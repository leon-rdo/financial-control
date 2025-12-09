from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import Category, Tag, Entity


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "type", "color_preview", "icon", "active", "created_at"]
    list_filter = ["type", "active", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at"]
    list_editable = ["active"]
    list_per_page = 50

    fieldsets = (
        (_("Basic Information"), {"fields": ("name", "type", "active")}),
        (_("Visual"), {"fields": ("color", "icon")}),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def color_preview(self, obj):
        if obj.color:
            return f'<div style="width: 20px; height: 20px; background-color: {obj.color}; border: 1px solid #ccc; border-radius: 3px;"></div>'
        return "-"

    color_preview.short_description = _("Color")
    color_preview.allow_tags = True

    actions = ["activate_categories", "deactivate_categories"]

    @admin.action(description=_("Activate selected categories"))
    def activate_categories(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, _(f"{updated} categories activated."))

    @admin.action(description=_("Deactivate selected categories"))
    def deactivate_categories(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, _(f"{updated} categories deactivated."))


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "color_preview", "created_at"]
    search_fields = ["name"]
    readonly_fields = ["created_at", "updated_at"]
    list_per_page = 50

    fieldsets = (
        (_("Basic Information"), {"fields": ("name", "color")}),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def color_preview(self, obj):
        if obj.color:
            return f'<div style="width: 20px; height: 20px; background-color: {obj.color}; border: 1px solid #ccc; border-radius: 3px;"></div>'
        return "-"

    color_preview.short_description = _("Color")
    color_preview.allow_tags = True


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "type",
        "document",
        "email",
        "phone",
        "active",
        "created_at",
    ]
    list_filter = ["type", "active", "created_at"]
    search_fields = ["name", "document", "email"]
    readonly_fields = ["created_at", "updated_at"]
    list_editable = ["active"]
    list_per_page = 50

    fieldsets = (
        (_("Basic Information"), {"fields": ("name", "type", "active")}),
        (_("Contact Information"), {"fields": ("document", "email", "phone")}),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    actions = ["activate_entities", "deactivate_entities"]

    @admin.action(description=_("Activate selected entities"))
    def activate_entities(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, _(f"{updated} entities activated."))

    @admin.action(description=_("Deactivate selected entities"))
    def deactivate_entities(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, _(f"{updated} entities deactivated."))
