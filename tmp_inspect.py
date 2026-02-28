import ast
from pathlib import Path
code = Path('bot/commands/rpg_cog.py').read_text(encoding='utf-8')
tree = ast.parse(code)
class ParentFinder(ast.NodeVisitor):
    def __init__(self):
        self.parents = []
        self.target = '_apply_meatwad_passive_effects'
    def visit(self, node):
        self.parents.append(node)
        super().visit(node)
        self.parents.pop()
    def visit_FunctionDef(self, node):
        if node.name == self.target:
            print('Function', node.name, 'parent stack:')
            for parent in self.parents[:-1]:
                print('  ', type(parent).__name__, getattr(parent, 'name', None))
        super().generic_visit(node)
    def visit_AsyncFunctionDef(self, node):
        if node.name == self.target:
            print('Async function', node.name, 'parent stack:')
            for parent in self.parents[:-1]:
                print('  ', type(parent).__name__, getattr(parent, 'name', None))
        super().generic_visit(node)
finder = ParentFinder()
finder.visit(tree)
