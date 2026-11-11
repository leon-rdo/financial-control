"""Modelos do assistente de IA (independente do canal: Telegram hoje, web depois)."""

from django.db import models


class Conversation(models.Model):
    """Uma conversa com o modelo. Fica presa a um provedor/modelo/prompt: se algum
    deles muda (ou após inatividade, ou /novo), uma conversa nova é aberta."""

    chat_id = models.BigIntegerField(db_index=True)
    channel = models.CharField(max_length=20, default="telegram")
    provider = models.CharField(max_length=20)
    model = models.CharField(max_length=100)
    prompt_hash = models.CharField(max_length=64)
    # Estado aguardado fora do LLM (ex.: senha de PDF). A resposta do usuário é
    # tratada pelo harness e nunca entra no histórico do modelo.
    awaiting = models.CharField(max_length=30, blank=True)
    awaiting_data = models.JSONField(default=dict, blank=True)
    # Avisos a injetar como mensagem de sistema antes da próxima mensagem do usuário
    pending_notes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_activity_at"]
        verbose_name = "Conversa"
        verbose_name_plural = "Conversas"

    def __str__(self):
        return f"Conversa #{self.pk} ({self.provider}/{self.model})"


class ChatMessage(models.Model):
    """Mensagem no formato nativo do provedor. O histórico só cresce: nunca editar
    mensagens antigas (o Claude valida os blocos de raciocínio contra o histórico)."""

    class Role(models.TextChoices):
        USER = "user", "Usuário"
        ASSISTANT = "assistant", "Assistente"
        TOOL = "tool", "Resultado de ferramenta"
        NOTE = "note", "Nota do sistema"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    native_content = models.JSONField()
    text_preview = models.TextField(blank=True)
    model = models.CharField(max_length=100, blank=True)
    stop_reason = models.CharField(max_length=30, blank=True)
    usage = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Mensagem"
        verbose_name_plural = "Mensagens"

    def __str__(self):
        return f"[{self.role}] {self.text_preview[:60]}"


class Attachment(models.Model):
    """Arquivo recebido (fatura, extrato, comprovante)."""

    class Kind(models.TextChoices):
        PDF = "pdf", "PDF"
        IMAGE = "image", "Imagem"
        TEXT = "text", "Texto (CSV/OFX)"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="attachments"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    filename = models.CharField(max_length=255)
    mime = models.CharField(max_length=100)
    size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True)
    storage_path = models.CharField(max_length=500)
    provider = models.CharField(max_length=20, blank=True)
    provider_file_id = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Anexo"
        verbose_name_plural = "Anexos"

    def __str__(self):
        return self.filename


class ImportBatch(models.Model):
    """Rascunho de lançamentos montado pela IA. Só vira registro real quando o
    usuário confirma (batch_service.commit)."""

    class Kind(models.TextChoices):
        INVOICE = "invoice", "Fatura de cartão"
        STATEMENT = "statement", "Extrato"
        RECEIPT = "receipt", "Comprovante"
        CHAT = "chat", "Conversa"

    class Status(models.TextChoices):
        STAGED = "staged", "Rascunho"
        COMMITTING = "committing", "Gravando"
        CONFIRMED = "confirmed", "Confirmado"
        DISCARDED = "discarded", "Descartado"
        UNDONE = "undone", "Desfeito"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="batches"
    )
    chat_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.CHAT)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.STAGED)
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=200, blank=True)

    # Fatura de cartão
    payment_method = models.ForeignKey(
        "accounts.PaymentMethod", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    invoice_year = models.PositiveSmallIntegerField(null=True, blank=True)
    invoice_month = models.PositiveSmallIntegerField(null=True, blank=True)
    invoice_total = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    invoice_due_date = models.DateField(null=True, blank=True)
    invoice_closing_date = models.DateField(null=True, blank=True)

    # Cartão/método ainda não cadastrado, criado na confirmação e usado como
    # método padrão do lote: {name, type, closing_day, due_day, bank_account_id, new_bank_account_name}
    new_payment_method = models.JSONField(default=dict, blank=True)
    # Outros cartões da mesma fatura ainda não cadastrados: [{name}], criados na
    # confirmação como cartões cobrados na fatura do cartão principal do lote.
    additional_new_cards = models.JSONField(default=list, blank=True)

    # Saldo informado (extrato ou chat): vira BalanceSnapshot na confirmação
    balance_account = models.ForeignKey(
        "accounts.BankAccount", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    balance_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    balance_date = models.DateField(null=True, blank=True)
    # Extrato: saldo inicial do período (confere com as linhas e o saldo final)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Saldos de outras contas/caixinhas: [{account_id | account_name, amount, date}]
    other_balances = models.JSONField(default=list, blank=True)

    attachment = models.ForeignKey(
        Attachment, on_delete=models.SET_NULL, null=True, blank=True, related_name="batches"
    )
    warnings = models.JSONField(default=list, blank=True)
    # O que o commit alterou fora dos itens (para desfazer): snapshot, cartão
    undo_data = models.JSONField(default=dict, blank=True)
    telegram_message_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    committed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lote de importação"
        verbose_name_plural = "Lotes de importação"

    def __str__(self):
        return f"Lote #{self.pk} ({self.get_kind_display()}, {self.get_status_display()})"


class StagedEntry(models.Model):
    """Um item do lote. As FKs para o que foi gravado ficam aqui (o app
    `financial` não depende do assistente)."""

    class Kind(models.TextChoices):
        EXPENSE = "EXPENSE", "Despesa"
        INCOME = "INCOME", "Receita"
        REFUND = "REFUND", "Estorno"
        INSTALLMENT_PURCHASE = "INSTALLMENT_PURCHASE", "Compra parcelada (nova)"
        INSTALLMENT_CHARGE = "INSTALLMENT_CHARGE", "Parcela em fatura"
        TRANSFER = "TRANSFER", "Transferência / pagamento de fatura"

    class Match(models.TextChoices):
        NEW = "new", "Novo"
        DUPLICATE = "duplicate", "Já registrado"
        WEAK = "weak_match", "Possível duplicado"
        CONFIRM_EXISTING = "confirm_existing", "Confirma lançamento previsto"

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="entries")
    position = models.PositiveIntegerField()
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()
    category = models.ForeignKey(
        "core.Category", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    category_name = models.CharField(max_length=100, blank=True)
    payment_method = models.ForeignKey(
        "accounts.PaymentMethod", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Cartão proposto no lote (ainda sem cadastro), resolvido na confirmação
    payment_method_name = models.CharField(max_length=100, blank=True)
    entity = models.ForeignKey(
        "core.Entity", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    entity_name = models.CharField(max_length=200, blank=True)
    installment_number = models.PositiveSmallIntegerField(null=True, blank=True)
    installments_total = models.PositiveSmallIntegerField(null=True, blank=True)
    external_id = models.CharField(max_length=120, blank=True)
    external_ref = models.CharField(max_length=100, blank=True)  # ex.: FITID do OFX
    notes = models.CharField(max_length=200, blank=True)

    # Só para TRANSFER
    from_account = models.ForeignKey(
        "accounts.BankAccount", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    to_account = models.ForeignKey(
        "accounts.BankAccount", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    to_card = models.ForeignKey(
        "accounts.PaymentMethod", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Caixinha/conta ainda sem cadastro (criada na confirmação dentro da conta do lote)
    from_account_name = models.CharField(max_length=100, blank=True)
    to_account_name = models.CharField(max_length=100, blank=True)
    paid_invoice_year = models.PositiveSmallIntegerField(null=True, blank=True)
    paid_invoice_month = models.PositiveSmallIntegerField(null=True, blank=True)

    match_status = models.CharField(max_length=20, choices=Match.choices, default=Match.NEW)
    match_note = models.CharField(max_length=255, blank=True)
    matched_transaction = models.ForeignKey(
        "financial.Transaction", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    matched_installment = models.ForeignKey(
        "financial.Installment", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    matched_transfer = models.ForeignKey(
        "financial.Transfer", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    include = models.BooleanField(default=True)

    committed_transaction = models.ForeignKey(
        "financial.Transaction", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="staged_entries",
    )
    committed_purchase = models.ForeignKey(
        "financial.Purchase", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="staged_entries",
    )
    committed_transfer = models.ForeignKey(
        "financial.Transfer", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="staged_entries",
    )
    # Estado anterior de um lançamento existente alterado no commit (para desfazer)
    previous_state = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["batch", "position"]
        unique_together = [["batch", "position"]]
        verbose_name = "Item do lote"
        verbose_name_plural = "Itens do lote"

    def __str__(self):
        return f"{self.position}. {self.description} R$ {self.amount}"


class ExtractionJob(models.Model):
    """Leitura de um documento em chamada única (assistant/extraction.py), feita
    na hora ("direct") ou pela API de batches ("batch", mais barata, assíncrona)."""

    class Mode(models.TextChoices):
        BATCH = "batch", "Batch (segundo plano)"
        DIRECT = "direct", "Na hora"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Enviado"
        DONE = "done", "Concluído"
        FALLBACK = "fallback", "Refeito pelo agente"
        FAILED = "failed", "Falhou"

    chat_id = models.BigIntegerField(db_index=True)
    attachment = models.ForeignKey(Attachment, on_delete=models.CASCADE, related_name="extraction_jobs")
    caption = models.TextField(blank=True)
    mode = models.CharField(max_length=10, choices=Mode.choices)
    model = models.CharField(max_length=100)
    provider_batch_id = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUBMITTED)
    error = models.TextField(blank=True)
    usage = models.JSONField(default=dict, blank=True)
    import_batch = models.ForeignKey(
        ImportBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name="extraction_jobs"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Extração de documento"
        verbose_name_plural = "Extrações de documentos"

    def __str__(self):
        return f"Extração #{self.pk} ({self.mode}, {self.status})"
