"""Exercise the actual inline workflow selectors without GitHub access."""
import contextlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / '.github/workflows/dependabot-rebase.yml'
RUN = yaml.safe_load(WORKFLOW.read_text())['jobs']['request-rebases']['steps'][0]['run']
BLOCKS = re.findall(r"<<'PY'\n(.*?)\nPY", RUN, re.S)


class DependabotQueueTests(unittest.TestCase):
    def select(self, prs, behind):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'prs.json'
            source.write_text(json.dumps(prs))
            def gh(args, **kwargs):
                if 'branches/main' in args[2]:
                    return 'mainsha\n'
                head = args[2].split('...')[-1]
                return str(behind[head]) + '\n'
            output = io.StringIO()
            with patch.object(sys, 'argv', ['selector', str(source)]), \
                 patch.dict(os.environ, {'REPOSITORY': 'owner/repo'}), \
                 patch('subprocess.check_output', side_effect=gh), \
                 patch('subprocess.run') as mutations, \
                 contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
                exec(BLOCKS[1], {})
            self.mutations = [call.args[0] for call in mutations.call_args_list]
            return output.getvalue().splitlines()

    def pr(self, number, state='UNKNOWN', body='Updates `vendor/app` from 1.2.0 to 1.3.0'):
        return dict(number=number, mergeStateStatus=state, headRefOid=str(number), body=body)

    def test_unknown_state_uses_ancestry_and_only_oldest_is_rebased(self):
        self.assertEqual(self.select([self.pr(301), self.pr(293)], {'301': 2, '293': 2}), ['293'])

    def test_current_oldest_blocks_next_until_checks_and_merge_finish(self):
        self.assertEqual(self.select([self.pr(301), self.pr(293)], {'293': 0}), [])
        self.assertEqual(len(self.mutations), 1)
        self.assertEqual(self.mutations[0][3], '293')
        self.assertIn('--auto', self.mutations[0])

    def test_later_auto_rebased_pr_loses_merge_eligibility_before_oldest_enabled(self):
        later = self.pr(301)
        later['autoMergeRequest'] = {'mergeMethod': 'REBASE'}
        self.select([later, self.pr(293)], {'293': 2})
        self.assertEqual(self.mutations[0], ['gh', 'pr', 'merge', '301', '--repo', 'owner/repo', '--disable-auto'])
        self.assertEqual(self.mutations[1][3], '293')
        self.assertIn('--match-head-commit', self.mutations[1])

    def test_draft_update_not_selected(self):
        draft = self.pr(292)
        draft['isDraft'] = True
        self.assertEqual(self.select([draft, self.pr(293)], {'293': 1}), ['293'])

    def test_major_update_not_automerged(self):
        self.assertEqual(self.select([self.pr(292, body='Updates `vendor/app` from 1.0.0 to 2.0.0'), self.pr(293)], {'293': 1}), ['293'])

    def test_failed_deployment_blocks_rebase(self):
        def gh(args, **kwargs):
            if args[2].endswith('branches/main'):
                return json.dumps({'commit': {'sha': 'mainsha'}})
            return json.dumps({'workflow_runs': [{'head_sha': 'mainsha', 'status': 'completed', 'conclusion': 'failure'}]})
        with patch.dict(os.environ, {'REPOSITORY': 'owner/repo'}), patch('subprocess.check_output', side_effect=gh):
            with self.assertRaisesRegex(SystemExit, 'deployment failed'):
                exec(BLOCKS[0], {})


if __name__ == '__main__':
    unittest.main()
