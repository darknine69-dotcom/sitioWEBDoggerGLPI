import os
import logging
from urllib.parse import quote

import msal
import requests

from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class GraphEmailBackend(BaseEmailBackend):
    """Envio de correos mediante Microsoft Graph OAuth 2.0."""

    def _get_token(self):
        app = msal.ConfidentialClientApplication(
            client_id=os.environ["MS_GRAPH_CLIENT_ID"],
            authority=(
                "https://login.microsoftonline.com/"
                + os.environ["MS_GRAPH_TENANT_ID"]
            ),
            client_credential=os.environ["MS_GRAPH_CLIENT_SECRET"],
        )

        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )

        if "access_token" not in result:
            raise RuntimeError(
                "No se pudo obtener el token OAuth de Microsoft Graph"
            )

        return result["access_token"]

    def send_messages(self, email_messages):
        if not email_messages:
            return 0

        try:
            token = self._get_token()
            sender = os.environ["MS_GRAPH_SENDER"]

            url = (
                "https://graph.microsoft.com/v1.0/users/"
                + quote(sender, safe="")
                + "/sendMail"
            )

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            sent = 0

            for message in email_messages:
                if message.attachments:
                    raise NotImplementedError(
                        "Adjuntos no implementados en GraphEmailBackend"
                    )

                if message.from_email and (
                    message.from_email.lower() != sender.lower()
                ):
                    raise ValueError(
                        "Remitente distinto al autorizado"
                    )

                content = message.body
                content_type = "Text"

                for alternative in getattr(
                    message, "alternatives", []
                ):
                    body, mimetype = alternative
                    if mimetype == "text/html":
                        content = body
                        content_type = "HTML"
                        break

                def recipients(addresses):
                    return [
                        {"emailAddress": {"address": address}}
                        for address in addresses
                    ]

                payload = {
                    "message": {
                        "subject": message.subject,
                        "body": {
                            "contentType": content_type,
                            "content": content,
                        },
                        "toRecipients": recipients(message.to),
                        "ccRecipients": recipients(message.cc),
                        "bccRecipients": recipients(message.bcc),
                    },
                    "saveToSentItems": True,
                }

                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=20,
                )

                if response.status_code != 202:
                    raise RuntimeError(
                        "Microsoft Graph rechazó el correo. "
                        f"HTTP {response.status_code}"
                    )

                sent += 1

            return sent

        except Exception as exc:
            logger.error("Error enviando correo con Graph (%s)", type(exc).__name__)
            if not self.fail_silently:
                raise
            return 0
