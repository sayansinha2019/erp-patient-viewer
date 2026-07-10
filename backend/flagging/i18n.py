"""Localized flag copy."""

from __future__ import annotations

MESSAGES = {
    "urgent_referral_title": {
        "en": "Urgent referral",
        "de": "Dringende Überweisung",
        "tr": "Acil sevk",
        "ar": "إحالة عاجلة",
        "ru": "Срочное направление",
        "fr": "Orientation urgente",
    },
    "urgent_referral_body": {
        "en": "This referral is marked urgent. Please book the specialist appointment soon.",
        "de": "Diese Überweisung ist als dringend gekennzeichnet. Bitte vereinbaren Sie bald einen Termin.",
        "tr": "Bu sevk acil olarak işaretlenmiş. Lütfen yakında randevu alın.",
        "ar": "هذه الإحالة عاجلة. يرجى حجز موعد مع الأخصائي قريباً.",
        "ru": "Направление помечено как срочное. Запишитесь к специалисту в ближайшее время.",
        "fr": "Cette orientation est urgente. Prenez rendez-vous avec le spécialiste bientôt.",
    },
}


def translate_flag(key: str, lang: str) -> str:
    entry = MESSAGES.get(key, {})
    return entry.get(lang) or entry.get("en") or key
