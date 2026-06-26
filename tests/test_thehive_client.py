import unittest
from datetime import datetime, timezone
from src.thehive_mcp.thehive_client import parse_date_to_ms, TheHiveClient

class TestTheHiveClient(unittest.TestCase):
    def test_parse_date_to_ms_integer(self):
        self.assertEqual(parse_date_to_ms(1719316800000), 1719316800000)
        self.assertEqual(parse_date_to_ms(1719316800000.0), 1719316800000)

    def test_parse_date_to_ms_digit_string(self):
        self.assertEqual(parse_date_to_ms("1719316800000"), 1719316800000)

    def test_parse_date_to_ms_iso_z(self):
        # 2026-06-25T12:00:00Z
        ms = parse_date_to_ms("2026-06-25T12:00:00Z")
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 25)
        self.assertEqual(dt.hour, 12)

    def test_parse_date_to_ms_iso_offset(self):
        # 2026-06-25T12:00:00+02:00
        ms = parse_date_to_ms("2026-06-25T12:00:00+02:00")
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        # 12:00:00+02:00 is 10:00:00 UTC
        self.assertEqual(dt.hour, 10)

    def test_parse_date_to_ms_simple_date(self):
        # 2026-06-25
        ms = parse_date_to_ms("2026-06-25")
        dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 6)
        self.assertEqual(dt.day, 25)
        self.assertEqual(dt.hour, 0)

    def test_search_alerts_query_ops(self):
        # Instantiate with dummy configuration so we can test query generation
        client = TheHiveClient(base_url="http://dummy", api_key="dummy_key")
        
        # Test search_alerts with sorting and date range filters
        # We override self.query to inspect what operations are passed to it
        actual_ops = []
        def dummy_query(ops, limit=10):
            nonlocal actual_ops
            actual_ops = ops
            return []
        
        client.query = dummy_query
        
        client.search_alerts(
            title="Phishing",
            sort="-_createdAt",
            created_after="2026-06-25T00:00:00Z",
            created_before="2026-06-25T23:59:59Z",
            limit=20
        )
        
        # We expect:
        # 1. listAlert
        # 2. filter for title
        # 3. filter for gte _createdAt
        # 4. filter for lte _createdAt
        # 5. sort by _createdAt desc
        self.assertEqual(actual_ops[0], {"_name": "listAlert"})
        
        # Filter 1: title contains "Phishing"
        self.assertEqual(actual_ops[1]["_name"], "filter")
        self.assertEqual(actual_ops[1]["_like"]["_field"], "title")
        self.assertEqual(actual_ops[1]["_like"]["_value"], "Phishing")
        
        # Filter 2: gte _createdAt
        self.assertEqual(actual_ops[2]["_name"], "filter")
        self.assertEqual(actual_ops[2]["_gte"]["_field"], "_createdAt")
        # 2026-06-25T00:00:00Z
        self.assertEqual(actual_ops[2]["_gte"]["_value"], parse_date_to_ms("2026-06-25T00:00:00Z"))
        
        # Filter 3: lte _createdAt
        self.assertEqual(actual_ops[3]["_name"], "filter")
        self.assertEqual(actual_ops[3]["_lte"]["_field"], "_createdAt")
        # 2026-06-25T23:59:59Z
        self.assertEqual(actual_ops[3]["_lte"]["_value"], parse_date_to_ms("2026-06-25T23:59:59Z"))
        
        # Sort: _createdAt desc
        self.assertEqual(actual_ops[4]["_name"], "sort")
        self.assertEqual(actual_ops[4]["_fields"], [{"_createdAt": "desc"}])

    def test_get_case_observables_query_ops(self):
        client = TheHiveClient(base_url="http://dummy", api_key="dummy_key")
        actual_ops = []
        def dummy_query(ops, limit=10):
            nonlocal actual_ops
            actual_ops = ops
            return []
        
        client.query = dummy_query
        client.get_case_observables(
            case_id="~1234",
            sort="-_createdAt",
            created_after="2026-06-25T00:00:00Z"
        )
        
        self.assertEqual(actual_ops[0], {"_name": "getCase", "idOrName": "~1234"})
        self.assertEqual(actual_ops[1], {"_name": "observables"})
        self.assertEqual(actual_ops[2]["_name"], "filter")
        self.assertEqual(actual_ops[2]["_gte"]["_field"], "_createdAt")
        self.assertEqual(actual_ops[3]["_name"], "sort")
        self.assertEqual(actual_ops[3]["_fields"], [{"_createdAt": "desc"}])

    def test_get_case_tasks_query_ops(self):
        client = TheHiveClient(base_url="http://dummy", api_key="dummy_key")
        actual_ops = []
        def dummy_query(ops, limit=10):
            nonlocal actual_ops
            actual_ops = ops
            return []
        
        client.query = dummy_query
        client.get_case_tasks(
            case_id="~1234",
            sort="-_createdAt",
            created_before="2026-06-25T23:59:59Z"
        )
        
        self.assertEqual(actual_ops[0], {"_name": "getCase", "idOrName": "~1234"})
        self.assertEqual(actual_ops[1], {"_name": "tasks"})
        self.assertEqual(actual_ops[2]["_name"], "filter")
        self.assertEqual(actual_ops[2]["_lte"]["_field"], "_createdAt")
        self.assertEqual(actual_ops[3]["_name"], "sort")
        self.assertEqual(actual_ops[3]["_fields"], [{"_createdAt": "desc"}])

    def test_search_alerts_custom_json_query(self):
        client = TheHiveClient(base_url="http://dummy", api_key="dummy_key")
        actual_ops = []
        def dummy_query(ops, limit=10):
            nonlocal actual_ops
            actual_ops = ops
            return []
        
        client.query = dummy_query
        
        # 1. Custom dict query representing a filter
        client.search_alerts(
            query='{"_eq": {"_field": "status", "_value": "New"}}'
        )
        self.assertEqual(actual_ops[0], {"_name": "listAlert"})
        self.assertEqual(actual_ops[1], {"_name": "filter", "_eq": {"_field": "status", "_value": "New"}})
        
        # 2. Custom dict query containing a named operation
        client.search_alerts(
            query='{"_name": "filter", "_eq": {"_field": "status", "_value": "Ignored"}}'
        )
        self.assertEqual(actual_ops[1], {"_name": "filter", "_eq": {"_field": "status", "_value": "Ignored"}})
        
        # 3. Custom list of operations
        client.search_alerts(
            query='[{"_name": "filter", "_eq": {"_field": "status", "_value": "Imported"}}]'
        )
        self.assertEqual(actual_ops[1], {"_name": "filter", "_eq": {"_field": "status", "_value": "Imported"}})
        
        # 4. Invalid JSON
        with self.assertRaises(ValueError):
            client.search_alerts(query='{invalid json}')

if __name__ == "__main__":
    unittest.main()
