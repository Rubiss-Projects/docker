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

    def test_failed_checks_release_queue_and_disable_old_automerge(self):
        for conclusion in ['FAILURE', 'CANCELLED', 'TIMED_OUT', 'ACTION_REQUIRED']:
            with self.subTest(conclusion=conclusion):
                failed = self.pr(292)
                failed['statusCheckRollup'] = [dict(status='COMPLETED', conclusion=conclusion)]
                failed['autoMergeRequest'] = {'mergeMethod': 'REBASE'}
                self.assertEqual(self.select([failed, self.pr(293)], {'293': 1}), ['293'])
                self.assertIn('--disable-auto', self.mutations[0])
                self.assertEqual(self.mutations[0][3], '292')

    def test_failed_legacy_status_releases_queue(self):
        failed = self.pr(292)
        failed['statusCheckRollup'] = [{'__typename': 'StatusContext', 'state': 'ERROR'}]
        self.assertEqual(self.select([failed, self.pr(293)], {'293': 1}), ['293'])

    def test_pending_checks_keep_queue_position(self):
        pending = self.pr(292)
        pending['statusCheckRollup'] = [dict(status='IN_PROGRESS', conclusion=None)]
        self.select([pending, self.pr(293)], {'292': 0})
        self.assertEqual(self.mutations[0][3], '292')

    def test_no_healthy_candidate_disables_automerge(self):
        failed = self.pr(292)
        failed['statusCheckRollup'] = [dict(status='COMPLETED', conclusion='FAILURE')]
        failed['autoMergeRequest'] = {'mergeMethod': 'REBASE'}
        self.assertEqual(self.select([failed], {}), [])
        self.assertEqual(len(self.mutations), 1)
        self.assertIn('--disable-auto', self.mutations[0])

    def test_both_classifiers_agree_on_supported_updates(self):
        workflow = WORKFLOW.with_name('dependabot-auto-merge.yml')
        run = yaml.safe_load(workflow.read_text())['jobs']['enable-automerge']['steps'][0]['run']
        classifier = re.search(r"<<'PY'.*?\n(.*?)\nPY", run, re.S).group(1)
        cases = [
            ('1.2.0', '1.3.0', True),
            ('`1.2.0`', '`1.2.1`', True),
            ('`4813745`', '`d6caeca`', True),
            ('5.8.0', '5.8.0', True),
            ('`1.2.0`', '`2.0.0`', False),
            ('1.3.0', '1.2.0', False),
            ('`unknown`', '`another`', False),
        ]
        for old, new, eligible in cases:
            with self.subTest(old=old, new=new):
                pr = self.pr(292, body=f'Updates `vendor/app` from {old} to {new}')
                self.assertEqual(self.select([pr], {'292': 1}), ['292'] if eligible else [])
                with tempfile.TemporaryDirectory() as directory:
                    event = Path(directory) / 'event.json'
                    event.write_text(json.dumps({'pull_request': pr}))
                    output = io.StringIO()
                    with patch.dict(os.environ, {'GITHUB_EVENT_PATH': str(event)}), contextlib.redirect_stdout(output):
                        exec(classifier, {})
                    self.assertIn(f'eligible={str(eligible).lower()}', output.getvalue())

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
