import csv
import logging
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Entity, PaymentMethod
from financial.models import Category, FinancialRecord, Installment

# Configura o logger para este módulo
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def parse_float_br(value_str):
    """
    Converte uma string formatada no padrão brasileiro para float.
    Exemplo: "R$ 1.400,10" será convertido para 1400.10.
    """
    value_str = value_str.strip().replace("R$", "").strip()
    if "," in value_str:
        parts = value_str.split(",")
        integer_part = parts[0].replace(".", "").strip()
        decimal_part = parts[1].strip()
        normalized = integer_part + "." + decimal_part
    else:
        normalized = value_str.replace(".", "")
    return float(normalized)


class Command(BaseCommand):
    help = "Importa os arquivos CSV para as tabelas do sistema financeiro"

    def add_arguments(self, parser):
        parser.add_argument(
            "--entities",
            type=str,
            default="entities.csv",
            help="Caminho para entities.csv",
        )
        parser.add_argument(
            "--payment_methods",
            type=str,
            default="payment_methods.csv",
            help="Caminho para payment_methods.csv",
        )
        parser.add_argument(
            "--incomes",
            type=str,
            default="incomes.csv",
            help="Caminho para incomes.csv",
        )
        parser.add_argument(
            "--expenses",
            type=str,
            default="expenses.csv",
            help="Caminho para expenses.csv",
        )
        parser.add_argument(
            "--installments",
            type=str,
            default="installments.csv",
            help="Caminho para installments.csv",
        )

    def handle(self, *args, **options):
        entities_path = options["entities"]
        payment_methods_path = options["payment_methods"]
        incomes_path = options["incomes"]
        expenses_path = options["expenses"]
        installments_path = options["installments"]

        logger.info("Iniciando a importação dos CSVs...")

        # Dicionários para mapear registros pelos IDs dos CSVs
        entities_map = {}
        payment_methods_map = {}
        record_map = {}

        try:
            with transaction.atomic():
                # Importa entidades
                with open(entities_path, newline="", encoding="utf-8-sig") as file:
                    reader = csv.DictReader(file, delimiter=";")
                    for row in reader:
                        entity_id = row["id"].strip()
                        name = row["Nome"].strip() if row["Nome"] else "Desconhecido"
                        description = (
                            row["Descrição"].strip() if row["Descrição"] else ""
                        )
                        document = row["CNPJ"].strip() if row["CNPJ"] else ""
                        person_type = (
                            "J" if document else "F"
                        )  # Pessoa jurídica se houver CNPJ
                        entity = Entity.objects.create(
                            name=name,
                            description=description,
                            person_type=person_type,
                            document=document,
                        )
                        entities_map[entity_id] = entity
                        logger.debug(f"Entidade criada: {entity}")
                logger.info("Entidades importadas com sucesso.")

                # Importa métodos de pagamento e mapeia o ID antigo ao novo objeto
                with open(
                    payment_methods_path, newline="", encoding="utf-8-sig"
                ) as file:
                    reader = csv.DictReader(file, delimiter=";")
                    for row in reader:
                        old_pm_id = row["id"].strip()
                        dono_name = row["dono"].strip()
                        owner = None
                        for entity in entities_map.values():
                            if entity.name == dono_name:
                                owner = entity
                                break
                        if not owner:
                            logger.warning(
                                f"Entidade com nome '{dono_name}' não encontrada para método de pagamento. Ignorando."
                            )
                            continue
                        fin_institution = row["Instituição financeira"].strip()
                        new_pm = PaymentMethod.objects.create(
                            fin_institution=fin_institution, owner=owner
                        )
                        payment_methods_map[old_pm_id] = new_pm
                        logger.debug(
                            f"Método de pagamento criado para {owner.name}: {fin_institution} (ID antigo: {old_pm_id})"
                        )
                logger.info("Métodos de pagamento importados com sucesso.")

                # Importa receitas (incomes)
                with open(incomes_path, newline="", encoding="utf-8-sig") as file:
                    reader = csv.DictReader(file, delimiter=";")
                    for row in reader:
                        income_id = row["id"].strip()
                        date_str = row["Data"].strip()
                        try:
                            date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
                        except ValueError as e:
                            logger.error(
                                f"Data inválida ({date_str}) em receita. Registro ignorado. Erro: {e}"
                            )
                            continue
                        try:
                            amount = parse_float_br(row["Valor"])
                        except ValueError as e:
                            logger.error(
                                f"Valor inválido ({row['Valor']}) em receita. Registro ignorado. Erro: {e}"
                            )
                            continue

                        entidade_id = row["Entidade"].strip()
                        try:
                            entity = entities_map[entidade_id]
                        except KeyError:
                            logger.error(
                                f"Entidade com ID {entidade_id} não encontrada em receita. Registro ignorado."
                            )
                            continue

                        # Não atribui forma de pagamento para incomes
                        payment_method = None

                        cat_name = (
                            row["Categoria"].strip() if row["Categoria"] else "Receitas"
                        )
                        category_obj, created = Category.objects.get_or_create(
                            name=cat_name,
                            defaults={
                                "description": f"Categoria {cat_name}",
                                "is_income": True,
                            },
                        )
                        if created:
                            logger.info(f"Categoria de receita criada: {cat_name}")

                        fin_record = FinancialRecord.objects.create(
                            amount=amount,
                            description=row["Descrição"].strip(),
                            entity=entity,
                            payment_method=payment_method,
                            date=date_obj,
                            category=category_obj,
                        )
                        record_map[income_id] = fin_record

                        Installment.objects.create(
                            fin_record=fin_record,
                            installment_number=1,
                            due_date=date_obj.replace(day=1),
                            amount=amount,
                            is_paid=True,
                        )
                        logger.debug(
                            f"Parcela criada para receita {income_id}: Parcela 1"
                        )
                        logger.debug(f"Receita criada: {fin_record}")
                logger.info("Receitas importadas com sucesso.")

                # Importa despesas (expenses)
                with open(expenses_path, newline="", encoding="utf-8-sig") as file:
                    reader = csv.DictReader(file, delimiter=";")
                    for row in reader:
                        expense_id = row["id"].strip()
                        date_str = row["Data"].strip()
                        try:
                            date_obj = datetime.strptime(date_str, "%d/%m/%Y").date()
                        except ValueError as e:
                            logger.error(
                                f"Data inválida ({date_str}) em despesa. Registro ignorado. Erro: {e}"
                            )
                            continue

                        try:
                            amount = parse_float_br(row["Valor"])
                        except ValueError as e:
                            logger.error(
                                f"Valor inválido ({row['Valor']}) em despesa. Registro ignorado. Erro: {e}"
                            )
                            continue

                        amount = -abs(amount)  # Garante valor negativo
                        description = row["Descrição"].strip()

                        recebedor_id = row["Recebedor"].strip()
                        entity = entities_map.get(recebedor_id)
                        if entity is None:
                            logger.warning(
                                f"Entidade com ID {recebedor_id} não encontrada em despesa. Registrando sem entidade."
                            )

                        old_pm_id = row["Forma de Pagamento"].strip()
                        payment_method = payment_methods_map.get(old_pm_id)
                        if not payment_method:
                            logger.warning(
                                f"Método de pagamento '{old_pm_id}' não encontrado para despesa. Registro ignorado."
                            )
                            continue

                        cat_name = (
                            row["Categoria"].strip() if row["Categoria"] else "Despesas"
                        )
                        category_obj, created = Category.objects.get_or_create(
                            name=cat_name,
                            defaults={
                                "description": f"Categoria {cat_name}",
                                "is_income": False,
                            },
                        )
                        if created:
                            logger.info(f"Categoria de despesa criada: {cat_name}")

                        fin_record = FinancialRecord.objects.create(
                            amount=amount,
                            description=description,
                            entity=entity,
                            payment_method=payment_method,
                            date=date_obj,
                            category=category_obj,
                        )
                        record_map[expense_id] = fin_record
                        logger.debug(f"Despesa criada: {fin_record}")
                logger.info("Despesas importadas com sucesso.")

                # Importa parcelas (installments)
                with open(installments_path, newline="", encoding="utf-8-sig") as file:
                    reader = csv.DictReader(file, delimiter=";")
                    for row in reader:
                        lancamento_key = row["Lançamento"].strip()
                        if lancamento_key not in record_map:
                            logger.warning(
                                f"Registro financeiro não encontrado para parcela (Lançamento: {lancamento_key}). Parcela ignorada."
                            )
                            continue

                        parent = record_map[lancamento_key]

                        try:
                            year = int(row["ANO"])
                            month = int(row["Mês"])
                        except ValueError as e:
                            logger.error(
                                f"ANO ou Mês inválidos em parcela. Parcela ignorada. Erro: {e}"
                            )
                            continue

                        due_date = datetime(year=year, month=month, day=1).date()

                        try:
                            raw = parse_float_br(row["Valor"])
                        except ValueError as e:
                            logger.error(
                                f"Valor inválido ({row['Valor']}) na parcela. Parcela ignorada. Erro: {e}"
                            )
                            continue

                        # Garante que parcelas de expenses fiquem negativas
                        installment_amount = raw * (-1 if parent.amount < 0 else 1)

                        try:
                            installment_number = int(row["Nº da Parcela"])
                        except ValueError as e:
                            logger.error(
                                f"Nº da Parcela inválido ({row['Nº da Parcela']}). Parcela ignorada. Erro: {e}"
                            )
                            continue

                        Installment.objects.create(
                            fin_record=parent,
                            installment_number=installment_number,
                            due_date=due_date,
                            amount=installment_amount,
                            is_paid=True,
                        )
                        logger.debug(
                            f"Parcela criada para lançamento {lancamento_key}: Parcela {installment_number}"
                        )
                logger.info("Parcelas importadas com sucesso.")

        except Exception as e:
            logger.exception(f"Erro durante a importação: {e}")
            raise CommandError(f"Erro durante a importação: {e}")

        logger.info("Importação concluída com sucesso.")
        self.stdout.write("Importação concluída com sucesso.")
