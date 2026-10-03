#!/usr/bin/env python3
"""Mutation testing with the standard library only (skeleton)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mutant:
    start: int
    end: int
    text: str
    line: int
    label: str


def generate(source, strings=True):
    return []


def apply(source, mutant):
    return source


def run_mutants(root, script, tests, workers=4, timeout=60):
    return []


def main(argv=None):
    return 0
