"""Regression checks for Doxygen's Python input adapter (standard library only)."""
import ast
import unittest

from filter_python import filter_source


class FilterSourceTests(unittest.TestCase):
    def filtered(self, source):
        result = filter_source(source)
        self.assertEqual(source.count("\n"), result.count("\n"))
        tree = ast.parse(result)
        self.assertFalse(any(isinstance(n, ast.AnnAssign) for n in ast.walk(tree)))
        return result, tree

    def test_required_field_keeps_documentation_and_name(self):
        source = "class Page:\n    ## @brief Номер страницы.\n    page: int\n"
        result, tree = self.filtered(source)
        self.assertIn("## @brief Номер страницы.", result)
        field = tree.body[0].body[0]
        self.assertEqual(field.targets[0].id, "page")
        self.assertIs(field.value.value, Ellipsis)

    def test_orm_default_is_preserved(self):
        source = 'id: Mapped[int] = mapped_column(\n    BigInteger, primary_key=True\n)\n'
        _, tree = self.filtered(source)
        self.assertEqual(ast.dump(tree.body[0].value), ast.dump(ast.parse(source).body[0].value))

    def test_multiline_parenthesized_annotation(self):
        source = 'names: (\n    list[str]\n) = (\n    ["x"]\n)\n'
        _, tree = self.filtered(source)
        self.assertEqual(ast.dump(tree.body[0].value), ast.dump(ast.parse(source).body[0].value))

    def test_unicode_and_equals_in_annotation(self):
        source = 'имя: Literal["a=b"] = "значение"\n'
        _, tree = self.filtered(source)
        self.assertEqual(tree.body[0].targets[0].id, "имя")
        self.assertEqual(tree.body[0].value.value, "значение")

    def test_multiline_required_field(self):
        _, tree = self.filtered('names: list[\n    str\n]\n')
        self.assertIs(tree.body[0].value.value, Ellipsis)

    def test_functions_and_plain_assignments_are_unchanged(self):
        source = 'limit = 10\ndef f(value: int | None = None) -> bool:\n    return value is None\n'
        self.assertEqual(filter_source(source), source)


if __name__ == "__main__":
    unittest.main()
