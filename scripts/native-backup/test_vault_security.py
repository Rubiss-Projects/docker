import json
import subprocess
import unittest
from unittest.mock import patch

import vault_security


class VaultCredentialTests(unittest.TestCase):
    def test_bootstrap_creation_skip_preserves_password_changes_and_other_roles(self):
        dump = b'CREATE ROLE app;\nALTER ROLE app PASSWORD \'fixture\';\nCREATE ROLE reader;\n'
        self.assertEqual(vault_security.roles_for_existing_bootstrap(dump, 'app'),
                         b'ALTER ROLE app PASSWORD \'fixture\';\nCREATE ROLE reader;\n')
        for invalid in [b'ALTER ROLE app LOGIN;\n', dump+b'CREATE ROLE "app";\n']:
            with self.assertRaises(ValueError):
                vault_security.roles_for_existing_bootstrap(invalid, 'app')

    def test_multiline_psql_aggregates_preserve_each_complete_json_value(self):
        values = [[{'role': 'first'}, {'role': 'a\nsecond'}], [], {'acl': ['x', 'y']}]
        output = ('\n'.join(json.dumps(v, indent=2) for v in values)+'\n').encode()
        self.assertEqual(vault_security.json_values(output), values)

    def test_saved_password_is_stdin_only_and_shell_quoted(self):
        password = "spaces ' $() ` ; secret"
        credentials = {'user': 'bitwarden', 'database': 'vault', 'password': password}
        with patch.object(vault_security.subprocess, 'run', return_value=
                          subprocess.CompletedProcess([], 0, b'1\n', b'')) as run:
            vault_security.verify_login('isolated-helper', credentials)
        args, kwargs = run.call_args
        self.assertNotIn(password, repr(args))
        self.assertIn(b"export PGPASSWORD=", kwargs['input'])
        self.assertEqual(args[0], ['docker', 'exec', '-i', 'isolated-helper', 'sh', '-s'])

    def test_failed_or_wrong_database_response_never_passes_authentication(self):
        for code, out in [(1, b''), (0, b'0\n'), (0, b'')]:
            with self.subTest(code=code, out=out), patch.object(vault_security.subprocess, 'run',
                    return_value=subprocess.CompletedProcess([], code, out, b'private password diagnostic')):
                with self.assertRaisesRegex(ValueError, 'authentication failed'):
                    vault_security.verify_login('helper', {'user': 'u', 'database': 'd', 'password': 'p'})

    def test_empty_role_or_object_inventory_is_rejected(self):
        for roles, objects in [([], [['table']]), ([{'rolname': 'app'}], [])]:
            output = ('\n'.join(json.dumps(v) for v in [roles, [], []])+'\n').encode()
            with self.subTest(roles=roles, objects=objects), self.assertRaises(ValueError):
                vault_security.inventory(lambda *a, **kw: output if kw['input'] == vault_security.ROLE_SQL.encode()
                                         else ('\n'.join(json.dumps(v) for v in objects)).encode(), [])


if __name__ == '__main__':
    unittest.main()
