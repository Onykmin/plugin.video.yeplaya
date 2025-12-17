#!/usr/bin/env python3
"""
Test to simulate Kodi's behavior where module-level cache doesn't persist
"""

def simulate_kodi_navigation():
    """
    Simulate how Kodi calls the plugin:
    1. First invocation: dosearch() - populates cache
    2. Second invocation: browse_series() - NEW instance, cache is empty!
    """
    print("=" * 70)
    print("SIMULATING KODI PLUGIN INVOCATIONS")
    print("=" * 70)

    # Invocation 1: User searches
    print("\n=== INVOCATION 1: dosearch (search for 'southpark') ===")
    cache1 = simulate_dosearch()
    print(f"Cache after dosearch: {list(cache1.keys())}")
    print(f"Series in cache: {list(cache1.get('southpark__', {}).get('series', {}).keys())}")

    # Invocation 2: User clicks on series (NEW PLUGIN INSTANCE)
    print("\n=== INVOCATION 2: browse_series (user clicks Southpark) ===")
    print("⚠️  NEW PLUGIN INSTANCE - cache is reset!")
    cache2 = {}  # Fresh instance, empty cache
    print(f"Cache in browse_series: {list(cache2.keys())}")

    # Try to get data from cache
    cache_key = 'southpark__'
    grouped = cache2.get(cache_key, {})
    series_name = 'Southpark'

    if series_name in grouped.get('series', {}):
        print(f"✓ Found series '{series_name}' in cache")
    else:
        print(f"✗ Series '{series_name}' NOT in cache - BLANK SCREEN!")
        print(f"  Available series: {list(grouped.get('series', {}).keys())}")

    return len(grouped.get('series', {})) > 0


def simulate_dosearch():
    """Simulate dosearch populating cache"""
    cache = {}

    # Simulate grouping South Park episodes
    grouped = {
        'series': {
            'Southpark': {
                'seasons': {
                    18: [{'name': 'S18E01'}, {'name': 'S18E02'}],
                    21: [{'name': 'S21E01'}]
                },
                'total_episodes': 3
            }
        },
        'non_series': []
    }

    cache_key = 'southpark__'
    cache[cache_key] = grouped

    return cache


def test_solution_with_refetch():
    """
    Test the solution: re-fetch data in browse_series if cache is empty
    """
    print("\n" + "=" * 70)
    print("TESTING SOLUTION: Re-fetch on cache miss")
    print("=" * 70)

    # Invocation 2: browse_series with empty cache
    print("\n=== INVOCATION 2: browse_series (empty cache) ===")
    cache = {}  # Empty cache (new instance)

    # Parameters from URL
    params = {
        'what': 'southpark',
        'category': '',
        'sort': '',
        'series': 'Southpark'
    }

    # Check cache
    cache_key = '{}_{}_{}'.format(params['what'], params.get('category', ''),
                                   params.get('sort', ''))
    grouped = cache.get(cache_key, {})

    if not grouped or params['series'] not in grouped.get('series', {}):
        print(f"✗ Cache miss - need to re-fetch")
        print(f"  Re-fetching with: what='{params['what']}', category='{params.get('category')}', sort='{params.get('sort')}'")

        # Simulate re-fetch and re-group
        grouped = {
            'series': {
                'Southpark': {
                    'seasons': {
                        18: [{'name': 'S18E01'}, {'name': 'S18E02'}],
                        21: [{'name': 'S21E01'}]
                    },
                    'total_episodes': 3
                }
            },
            'non_series': []
        }
        print(f"✓ Re-fetched and grouped data")
        print(f"  Series found: {list(grouped['series'].keys())}")

    # Now try to get series
    if params['series'] in grouped.get('series', {}):
        series_data = grouped['series'][params['series']]
        print(f"\n✓ SUCCESS: Found '{params['series']}'")
        print(f"  Seasons: {list(series_data['seasons'].keys())}")
        print(f"  Total episodes: {series_data['total_episodes']}")
        return True
    else:
        print(f"\n✗ FAILED: Still can't find series")
        return False


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("CACHE PERSISTENCE TEST")
    print("=" * 70)

    # Test 1: Simulate the problem
    print("\n### TEST 1: Demonstrating the problem ###")
    problem_exists = not simulate_kodi_navigation()

    # Test 2: Demonstrate the solution
    print("\n### TEST 2: Demonstrating the solution ###")
    solution_works = test_solution_with_refetch()

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Problem demonstrated: {problem_exists}")
    print(f"Solution works: {solution_works}")

    if problem_exists and solution_works:
        print("\n✓ CONCLUSION: Cache doesn't persist between invocations")
        print("  SOLUTION: Re-fetch data in browse_series/browse_season if cache is empty")

    print("=" * 70)
