import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('startup_plan',Path(__file__).with_name('validate-startup-plan.py'))
review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.plan={'schemaVersion':1,'state':'preparation_only','automaticStartAllowed':False,'stacks':[{'stack':'one','compose':'one/docker-compose.yml','services':['one'],'disposition':'keep','releaseGates':['acceptance'],'after':[]}],'excludedComposePaths':[]}
        self.compositions={'one/docker-compose.yml':['one']}

    def test_new_definition_and_new_service_require_review(self):
        for definitions in ({**self.compositions,'new/docker-compose.yml':['new']},{'one/docker-compose.yml':['new','one']}):
            with self.assertRaises(ValueError):review.validate(self.plan,definitions)

    def test_cycles_and_accidental_activation_rejected(self):
        p=copy.deepcopy(self.plan);p['stacks'][0]['after']=['one']
        with self.assertRaises(ValueError):review.validate(p,self.compositions)
        p=copy.deepcopy(self.plan);p['automaticStartAllowed']=True
        with self.assertRaises(ValueError):review.validate(p,self.compositions)

    def test_unknown_container_and_unisolated_helper_rejected(self):
        container={'name':'/unknown','composeProject':'other','composeService':'other','networkMode':'none','portBindings':{},'mounts':[]}
        with self.assertRaises(ValueError):review.match_live(self.plan,{'containers':[container]},set())
        container['composeProject']=None;container['networkMode']='host'
        with self.assertRaises(ValueError):review.match_live(self.plan,{'containers':[container]},{'unknown'})


if __name__=='__main__':unittest.main()
