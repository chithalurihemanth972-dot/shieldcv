"""No console class may overwrite an attribute Textual itself uses.

Two real bugs came from this (``is_running`` stopped RunScreen mounting,
``_closed`` broke the splash's message loop), so every ``self.<name> = ...``
and ``@property`` in ``src/tui`` is checked against its Textual base class.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil

import src.tui
import src.tui.screens
import src.tui.widgets
from textual.dom import DOMNode


def _tui_classes():
    for package in (src.tui, src.tui.screens, src.tui.widgets):
        for info in pkgutil.iter_modules(package.__path__):
            if info.name == "__main__":
                continue
            module = importlib.import_module(f"{package.__name__}.{info.name}")
            for _, cls in inspect.getmembers(module, inspect.isclass):
                if cls.__module__ == module.__name__ and issubclass(cls, DOMNode):
                    yield cls


def _textual_base(cls):
    return next(base for base in cls.__mro__ if base.__module__.startswith("textual"))


def _textual_names(base) -> set:
    names = set(dir(base))
    try:
        names |= set(vars(base()))
    except Exception:  # bases that need constructor arguments
        pass
    return names


def _own_names(cls) -> set:
    tree = ast.parse(inspect.getsource(cls))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store) \
                and isinstance(node.value, ast.Name) and node.value.id == "self":
            names.add(node.attr)
        if isinstance(node, ast.FunctionDef) and any(
                isinstance(d, ast.Name) and d.id == "property" for d in node.decorator_list):
            names.add(node.name)
    return names


# Deliberate writes to Textual's public API, not accidental shadowing.
ALLOWED = {("ShieldApp", "theme")}


def test_no_tui_class_shadows_textual_attributes():
    clashes = []
    for cls in _tui_classes():
        base = _textual_base(cls)
        for name in sorted(_own_names(cls) & _textual_names(base)):
            if (cls.__name__, name) in ALLOWED:
                continue
            clashes.append(f"{cls.__module__}.{cls.__name__}.{name} (shadows {base.__name__})")
    assert not clashes, "\n".join(clashes)
