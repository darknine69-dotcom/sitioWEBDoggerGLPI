from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.tickets.forms import validar_contenido_adjunto
from apps.tickets.views_observador import _retorno_seguro
from apps.tickets.views_monitoreo import _retorno_monitoreo
from apps.tickets.views import _destino_seguro
from apps.tickets.models import Ticket, TicketAdjunto
from django.contrib.auth import get_user_model
from apps.accounts.views import _ruta_retorno_segura


class PrivateMediaAndUploadTest(SimpleTestCase):
    def test_redirect_allows_local_path_but_rejects_external_url(self):
        for target, expected in [('/panel/', '/panel/'), ('https://evil.example/phishing', reverse('tickets:obs_mi_lista')), ('//evil.example/', reverse('tickets:obs_mi_lista'))]:
            with self.subTest(target=target):
                request = RequestFactory().post('/', {'volver': target})
                self.assertEqual(_retorno_seguro(request, 'tickets:obs_mi_lista'), expected)

    def test_admin_and_ticket_redirects_reject_scheme_relative_hosts(self):
        request = RequestFactory().post('/', {'volver': '//evil.example/', 'next': '//evil.example/'})
        self.assertEqual(_retorno_monitoreo(request), reverse('tickets:monitoreo_admin'))
        self.assertEqual(_destino_seguro(request, 'tickets:lista'), reverse('tickets:lista'))
        self.assertEqual(_ruta_retorno_segura(request, 'next', reverse('accounts:ajustes')), reverse('accounts:ajustes'))

    def test_direct_ticket_attachment_url_is_not_public(self):
        self.assertEqual(Client().get('/media/adjuntos/HD-0001/example.pdf').status_code, 404)

    def test_spoofed_image_and_svg_are_rejected(self):
        for name, body in [('malicioso.png', b'<script>alert(1)</script>'), ('malicioso.svg', b'<svg/>')]:
            with self.subTest(name=name), self.assertRaises(ValidationError):
                validar_contenido_adjunto(SimpleUploadedFile(name, body, content_type='image/png'))

    def test_valid_image_is_verified_and_rewound(self):
        buffer = BytesIO()
        Image.new('RGB', (2, 2)).save(buffer, format='PNG')
        archivo = SimpleUploadedFile('imagen.png', buffer.getvalue(), content_type='text/plain')
        validar_contenido_adjunto(archivo)
        self.assertEqual(archivo.content_type, 'image/png')
        self.assertEqual(archivo.tell(), 0)

    def test_invalid_pdf_is_rejected(self):
        for contenido in (b'no es pdf', b'%PDF-1.7\ncontenido sin terminar'):
            with self.subTest(contenido=contenido), self.assertRaises(ValidationError):
                validar_contenido_adjunto(SimpleUploadedFile('documento.pdf', contenido, content_type='application/pdf'))

    def test_pdf_with_signature_and_end_marker_is_accepted_as_attachment(self):
        archivo = SimpleUploadedFile('documento.pdf', b'%PDF-1.4\n1 0 obj\nendobj\n%%EOF\n', content_type='text/plain')
        validar_contenido_adjunto(archivo)
        self.assertEqual(archivo.content_type, 'application/pdf')
        self.assertEqual(archivo.tell(), 0)


class AttachmentAuthorizationTest(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.owner = user_model.objects.create_user('owner@example.com', 'Dueño', 'clave', rol='usuario')
        self.other = user_model.objects.create_user('other@example.com', 'Otro', 'clave', rol='usuario')
        self.ticket = Ticket.objects.create(titulo='Original', descripcion='Detalle', solicitante_nombre='Dueño', solicitante_email=self.owner.email)

    def test_ajax_rejects_forged_image_without_changing_ticket(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('tickets:mi_api_editar', args=[self.ticket.pk]), {'titulo': 'Cambiado', 'descripcion': 'Cambio', 'imagen': SimpleUploadedFile('fake.png', b'<script>malicioso</script>', content_type='image/png')})
        self.assertEqual(response.status_code, 400)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.titulo, 'Original')
        self.assertFalse(TicketAdjunto.objects.filter(ticket=self.ticket).exists())

    def test_other_user_cannot_access_attachment_metadata(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse('tickets:mi_api_info', args=[self.ticket.pk]))
        self.assertEqual(response.status_code, 404)

    def test_empty_emails_do_not_grant_attachment_ownership(self):
        self.other.email = ""
        self.other.save(update_fields=["email"])
        self.ticket.solicitante_email = ""
        self.ticket.save(update_fields=["solicitante_email"])
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            adjunto = TicketAdjunto.objects.create(
                ticket=self.ticket, archivo=SimpleUploadedFile("archivo.pdf", b"%PDF-1.4\n%%EOF\n"),
                nombre_original="archivo.pdf", mime_type="application/pdf", tamano_bytes=15,
            )
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(reverse("tickets:adjunto", args=[adjunto.pk])).status_code, 404)
            self.assertEqual(self.client.get(reverse("tickets:chat_hilo", args=[self.ticket.pk])).status_code, 403)
            self.assertEqual(self.client.post(reverse("tickets:mi_presionar", args=[self.ticket.pk]), {"mensaje": "texto"}).status_code, 404)

    def test_ticket_attachment_view_checks_ownership_and_blocks_direct_url(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            adjunto = TicketAdjunto.objects.create(
                ticket=self.ticket,
                archivo=SimpleUploadedFile('test.pdf', b'%PDF-1.4\n%%EOF\n', content_type='application/pdf'),
                nombre_original='test.pdf', mime_type='application/pdf', tamano_bytes=15,
            )
            self.client.force_login(self.other)
            self.assertEqual(self.client.get(reverse('tickets:adjunto', args=[adjunto.pk])).status_code, 404)
            self.client.force_login(self.owner)
            self.assertEqual(self.client.get(adjunto.archivo.url).status_code, 404)
            response = self.client.get(reverse('tickets:adjunto', args=[adjunto.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
            response.close()

    def test_legacy_svg_content_type_is_always_downloaded(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            adjunto = TicketAdjunto.objects.create(
                ticket=self.ticket,
                archivo=SimpleUploadedFile('legacy.svg', b'<svg/>', content_type='image/svg+xml'),
                nombre_original='legacy.svg', mime_type='image/svg+xml; charset=utf-8', tamano_bytes=6,
            )
            self.client.force_login(self.owner)
            response = self.client.get(reverse('tickets:adjunto', args=[adjunto.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Type'], 'application/octet-stream')
            self.assertTrue(response['Content-Disposition'].startswith('attachment;'))
            response.close()
