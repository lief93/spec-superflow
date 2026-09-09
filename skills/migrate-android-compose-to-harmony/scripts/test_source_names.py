import unittest

from ui_migration.naming import NameScope, source_identifier
from ui_migration.frontend.source_names import property_name_hints, reference_name, direct_reference_name


class SourceNamesTest(unittest.TestCase):
    def test_plain_names_keep_original_case(self):
        self.assertEqual(source_identifier('profileScreen'), 'profileScreen')
        self.assertEqual(source_identifier('AccountCard'), 'AccountCard')

    def test_keywords_and_invalid_characters_are_legalized(self):
        self.assertEqual(source_identifier('class'), 'classValue')
        self.assertEqual(source_identifier('`account-name`'), 'account_name')
        self.assertEqual(source_identifier('2fa'), 'Component2fa')

    def test_suffixes_only_disambiguate_real_collisions(self):
        scope = NameScope(['title'])
        self.assertEqual(scope.allocate('title'), 'title2')
        self.assertEqual(scope.allocate('title'), 'title3')
        self.assertEqual(scope.allocate('subtitle'), 'subtitle')

    def test_member_reference_retains_name_not_expression_or_value(self):
        self.assertEqual(reference_name('account.balance'), 'balance')
        self.assertIsNone(reference_name('"balance"'))
        self.assertIsNone(reference_name('formatAmount(balance)'))

    def test_projected_value_keeps_original_reference(self):
        hints = property_name_hints({'type':'Text', 'arguments':{
            'semantic':{'text':{'expression':'"First"', 'original_expression':'title'}}}})
        self.assertEqual(hints, {'style.content.text':'title'})

    def test_display_name_is_not_proof_of_parameter_binding(self):
        self.assertEqual(direct_reference_name('title'), 'title')
        self.assertIsNone(direct_reference_name('account.title'))
        node = {'type':'Text', 'arguments':{'semantic':{'text':{
            'expression':'"Account title"', 'original_expression':'account.title'}}}}
        self.assertEqual(property_name_hints(node), {'style.content.text':'title'})
        self.assertEqual(property_name_hints(node, direct_only=True), {})


if __name__ == '__main__':
    unittest.main()
