"""Guard the deployment docs against the docker-compose interpolation gotcha (issue #4).

`docker compose` interpolates `.env` values, so a bare ``$`` in ``ADMIN_PASSWORD_HASH`` is read
as a variable reference and silently blanked -- with a real pbkdf2 hash that wipes out the salt
and hash segments and every login fails with a 500. The fix is documented in ``.env.example``
(escape each ``$`` to ``$$``; Compose unescapes it back inside the container), and it assumes
``docker-compose.yml`` passes the variable through with the bare ``- ADMIN_PASSWORD_HASH``
syntax (no ``${...}`` reference).

These tests keep ``docker-compose.yml`` and ``.env.example`` consistent so the two can't drift
apart again -- e.g. someone switching the compose file to ``${ADMIN_PASSWORD_HASH}``
references, or "fixing" ``.env.example`` to drop the escaping.
"""

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

REPO_ROOT = Path(settings.BASE_DIR)


class DeployConfigTests(SimpleTestCase):
    def test_compose_passes_admin_password_hash_with_bare_syntax(self):
        """docker-compose.yml must keep the bare `- ADMIN_PASSWORD_HASH` form (no ${...}
        reference), which is the form the .env.example escaping guidance assumes."""
        compose = (REPO_ROOT / "docker-compose.yml").read_text()
        self.assertIn("- ADMIN_PASSWORD_HASH", compose)
        self.assertNotIn("${ADMIN_PASSWORD_HASH}", compose)

    def test_env_example_documents_dollar_escaping(self):
        """.env.example must show the $$-escaped hash and warn that a bare $ is blanked."""
        env = (REPO_ROOT / ".env.example").read_text()
        self.assertIn("pbkdf2_sha256$$1500000$$abc$$def", env)
        self.assertIn('"$"', env)
        self.assertIn("blanked", env)

    def test_env_example_has_no_raw_pbkdf2_hash_value(self):
        """The ADMIN_PASSWORD_HASH value slot must never show a raw single-$ pbkdf2 hash,
        which would silently break login on modern docker compose if copied as-is."""
        env = (REPO_ROOT / ".env.example").read_text()
        self.assertNotIn("ADMIN_PASSWORD_HASH=pbkdf2_sha256$", env)
        # ...but the transformation example (raw -> escaped) is fine and expected.
        self.assertIn("pbkdf2_sha256$1500000$abc$def", env)

    def test_compose_passes_csrf_and_proxy_env_vars(self):
        """docker-compose.yml must pass CSRF_TRUSTED_ORIGINS and TRUST_X_FORWARDED_PROTO
        through to the containers (bare `- NAME` syntax), matching .env.example."""
        compose = (REPO_ROOT / "docker-compose.yml").read_text()
        self.assertIn("- CSRF_TRUSTED_ORIGINS", compose)
        self.assertIn("- TRUST_X_FORWARDED_PROTO", compose)
        self.assertNotIn("${CSRF_TRUSTED_ORIGINS}", compose)
        self.assertNotIn("${TRUST_X_FORWARDED_PROTO}", compose)

    def test_env_example_documents_csrf_trusted_origins(self):
        """.env.example must document CSRF_TRUSTED_ORIGINS and the 403 symptom it prevents."""
        env = (REPO_ROOT / ".env.example").read_text()
        self.assertIn("CSRF_TRUSTED_ORIGINS", env)
        self.assertIn("TRUST_X_FORWARDED_PROTO", env)
        self.assertIn("CSRF verification failed", env)
