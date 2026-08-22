"""Escolhe o canal de notificação pelo .env — é isto que main.py importa,
em vez de amarrar no Telegram.

A regra é uma só: se NOTIFICADOR_WEBHOOK_URL estiver preenchida, manda por
webhook (Discord/Slack); senão, Telegram. Sem variável de "modo" separada —
duas fontes de verdade pra mesma decisão é como se acaba com o .env dizendo
webhook e o robô postando no Telegram.

A escolha acontece uma vez, no import, não a cada mensagem: os dois módulos
expõem exatamente as mesmas cinco funções (mesmos nomes, mesma assinatura,
mesmo contrato de retorno), então trocar o import troca o canal inteiro sem
que main.py precise saber que existe mais de um.
"""

from core.config import NOTIFICADOR_WEBHOOK_URL
from core.logger import get_logger

if NOTIFICADOR_WEBHOOK_URL:
    from notifier.webhook import (  # noqa: F401
        enviar_digest,
        enviar_mensagem,
        notificar_vaga,
        notificar_vaga_exploratoria,
        processar_feedback_pendente,
    )

    _CANAL = "webhook (Discord/Slack)"
else:
    from notifier.telegram import (  # noqa: F401
        enviar_digest,
        enviar_mensagem,
        notificar_vaga,
        notificar_vaga_exploratoria,
        processar_feedback_pendente,
    )

    _CANAL = "Telegram"

# Log no import de propósito: silêncio no canal é o sintoma mais comum de
# problema aqui, e a primeira pergunta é sempre "ele está tentando mandar
# por onde?". Sem esta linha, descobrir isso exige ler o .env de dentro do
# container.
get_logger().info(f"Canal de notificação: {_CANAL}.")

__all__ = [
    "enviar_digest",
    "enviar_mensagem",
    "notificar_vaga",
    "notificar_vaga_exploratoria",
    "processar_feedback_pendente",
]
