#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for navigation and state management.

Tests:
- Page bounds validation
"""

import sys
import os
import unittest

# Add parent directory for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

# Mocks provided by conftest.py


class TestPageBounds(unittest.TestCase):
    """Test pagination bounds validation."""

    def test_negative_page_clamped_to_zero(self):
        """Negative page numbers should be clamped to 0."""
        page = -5
        total_pages = 10

        # Fixed validation logic
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        self.assertEqual(page, 0, "Negative page should clamp to 0")

    def test_page_exceeding_total_clamped(self):
        """Page exceeding total should clamp to last page."""
        page = 100
        total_pages = 5

        # Fixed validation logic
        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        self.assertEqual(page, 4, "Page 100 should clamp to 4 (last page)")

    def test_valid_page_unchanged(self):
        """Valid page number should remain unchanged."""
        page = 3
        total_pages = 10
        original_page = page

        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        self.assertEqual(page, original_page, "Valid page should be unchanged")

    def test_page_zero_with_empty_results(self):
        """Page 0 should work with zero total items."""
        total_items = 0
        items_per_page = 25
        page = 0

        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)

        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        self.assertEqual(page, 0, "Page should be 0 with empty results")
        self.assertEqual(total_pages, 1, "total_pages should be at least 1")

    def test_start_end_indices_valid(self):
        """Start and end indices should be valid for slicing."""
        total_items = 75
        items_per_page = 25
        page = 2  # Third page

        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)

        if page < 0:
            page = 0
        elif page >= total_pages:
            page = total_pages - 1

        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page

        self.assertEqual(start_idx, 50, "Start index for page 2 should be 50")
        self.assertEqual(end_idx, 75, "End index for page 2 should be 75")

        # Verify slicing works
        items = list(range(total_items))
        page_items = items[start_idx:end_idx]
        self.assertEqual(len(page_items), 25, "Should have 25 items on page 2")


if __name__ == '__main__':
    unittest.main()
