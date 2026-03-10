from django.db import migrations


DEFAULT_CATEGORIES = [
    # (name, type)
    ("Alimentação", "EXPENSE"),
    ("Moradia", "EXPENSE"),
    ("Despesa Veícular", "EXPENSE"),
    ("Imposto, taxa, contribuição", "EXPENSE"),
    ("Compras", "EXPENSE"),
    ("Cuidados Pessoais", "EXPENSE"),
    ("Doação e Caridade", "EXPENSE"),
    ("Lazer", "EXPENSE"),
    ("Estudos", "EXPENSE"),
    ("Saúde", "EXPENSE"),
    ("Telecomunicações", "EXPENSE"),
    ("Transporte", "EXPENSE"),
    ("Assinaturas e Serviços", "EXPENSE"),
    ("Pets", "EXPENSE"),
    ("Outros", "BOTH"),
    ("Salário", "INCOME"),
    ("Freelance", "INCOME"),
    ("Investimentos", "INCOME"),
    ("Outros Receitas", "INCOME"),
]


def create_default_categories(apps, schema_editor):
    Category = apps.get_model("core", "Category")
    for name, cat_type in DEFAULT_CATEGORIES:
        Category.objects.get_or_create(
            name=name,
            defaults={"type": cat_type, "active": True},
        )


def reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_categories, reverse),
    ]
