import os
import requests
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger("thehive_mcp.client")

def parse_date_to_ms(date_val: Any) -> int:
    """
    Parses various date/time formats into Unix timestamp in milliseconds.
    Supports integers, floats, string representation of integers, ISO 8601 strings.
    """
    if isinstance(date_val, (int, float)):
        return int(date_val)
    if isinstance(date_val, str):
        if date_val.isdigit():
            return int(date_val)
        # Normalize ISO representation
        normalized = date_val
        if normalized.endswith('Z'):
            normalized = normalized[:-1] + '+00:00'
        try:
            dt = datetime.fromisoformat(normalized)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except Exception:
            # Fallback to standard YYYY-MM-DD
            try:
                dt = datetime.strptime(date_val, "%Y-%m-%d")
                dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp() * 1000)
            except Exception:
                raise ValueError(
                    f"Could not parse date '{date_val}'. Expected ISO format (e.g. 2026-06-25T00:00:00Z) "
                    "or a millisecond timestamp."
                )
    raise ValueError(f"Unsupported date type: {type(date_val)}")

class TheHiveClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None, verify_ssl: Optional[bool] = None):
        # 1. Base URL normalization
        self.base_url = base_url or os.environ.get("THEHIVE_URL")
        if not self.base_url:
            raise ValueError("THEHIVE_URL environment variable or base_url parameter is required")
        self.base_url = self.base_url.rstrip("/")

        # 2. API Key setup
        self.api_key = api_key or os.environ.get("THEHIVE_API_KEY")
        if not self.api_key:
            raise ValueError("THEHIVE_API_KEY environment variable or api_key parameter is required")

        # 3. SSL verification handling
        if verify_ssl is not None:
            self.verify_ssl = verify_ssl
        else:
            env_verify = os.environ.get("THEHIVE_VERIFY_SSL", "true").lower()
            self.verify_ssl = env_verify not in ("false", "0", "no")

        # 4. Headers setup
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Optional organisation targeting
        org = os.environ.get("THEHIVE_ORG")
        if org:
            self.headers["X-Organisation"] = org

    def _post(self, path: str, json_data: Any = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = requests.post(url, headers=self.headers, json=json_data, verify=self.verify_ssl)
            response.raise_for_status()
            # Some endpoints return 204 No Content
            if response.status_code == 204:
                return {}
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on POST {path}: {e} - Response: {e.response.text if e.response else 'No response'}")
            raise RuntimeError(f"TheHive API returned HTTP error: {e.response.text if e.response else str(e)}")
        except Exception as e:
            logger.error(f"Error on POST {path}: {e}")
            raise RuntimeError(f"Failed to perform request to TheHive: {str(e)}")

    def _get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, headers=self.headers, verify=self.verify_ssl)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on GET {path}: {e} - Response: {e.response.text if e.response else 'No response'}")
            raise RuntimeError(f"TheHive API returned HTTP error: {e.response.text if e.response else str(e)}")
        except Exception as e:
            logger.error(f"Error on GET {path}: {e}")
            raise RuntimeError(f"Failed to perform request to TheHive: {str(e)}")

    def _patch(self, path: str, json_data: Any = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = requests.patch(url, headers=self.headers, json=json_data, verify=self.verify_ssl)
            response.raise_for_status()
            if response.status_code == 204:
                return {}
            try:
                return response.json()
            except ValueError:
                return {}
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error on PATCH {path}: {e} - Response: {e.response.text if e.response else 'No response'}")
            raise RuntimeError(f"TheHive API returned HTTP error: {e.response.text if e.response else str(e)}")
        except Exception as e:
            logger.error(f"Error on PATCH {path}: {e}")
            raise RuntimeError(f"Failed to perform request to TheHive: {str(e)}")

    def query(self, query_ops: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
        # Ensure pagination page size is specified if not present
        has_page = any(op.get("_name") == "page" for op in query_ops)
        if not has_page:
            query_ops.append({"_name": "page", "from": 0, "to": limit})
        
        payload = {"query": query_ops}
        result = self._post("/api/v1/query", json_data=payload)
        
        # If the result is a dict (e.g. error or wrapper), return as a list wrapper, but usually query returns a list of objects
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            return [result]
        return []

    # --- Case Methods ---
    def create_case(self, title: str, description: str, severity: int = 2, tags: Optional[List[str]] = None, tlp: int = 2, pap: int = 2, flag: bool = False) -> Dict[str, Any]:
        payload = {
            "title": title,
            "description": description,
            "severity": severity,
            "tags": tags or [],
            "tlp": tlp,
            "pap": pap,
            "flag": flag
        }
        return self._post("/api/v1/case", json_data=payload)

    def get_case(self, id_or_name: str) -> Dict[str, Any]:
        return self._get(f"/api/v1/case/{id_or_name}")

    def search_cases(
        self, 
        title: Optional[str] = None, 
        severity: Optional[int] = None, 
        tags: Optional[List[str]] = None, 
        status: Optional[str] = None, 
        sort: Optional[str] = None,
        created_after: Optional[Any] = None,
        created_before: Optional[Any] = None,
        query: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        query_ops = [{"_name": "listCase"}]
        
        if title:
            query_ops.append({
                "_name": "filter",
                "_like": {
                    "_field": "title",
                    "_value": title
                }
            })
        if severity is not None:
            query_ops.append({
                "_name": "filter",
                "_eq": {
                    "_field": "severity",
                    "_value": severity
                }
            })
        if status:
            query_ops.append({
                "_name": "filter",
                "_eq": {
                    "_field": "status",
                    "_value": status
                }
            })
        if tags:
            for tag in tags:
                query_ops.append({
                    "_name": "filter",
                    "_eq": {
                        "_field": "tags",
                        "_value": tag
                    }
                })
        if created_after is not None:
            ms = parse_date_to_ms(created_after)
            query_ops.append({
                "_name": "filter",
                "_gte": {
                    "_field": "_createdAt",
                    "_value": ms
                }
            })
        if created_before is not None:
            ms = parse_date_to_ms(created_before)
            query_ops.append({
                "_name": "filter",
                "_lte": {
                    "_field": "_createdAt",
                    "_value": ms
                }
            })
        if query:
            import json
            try:
                parsed = json.loads(query)
                if isinstance(parsed, list):
                    for op in parsed:
                        if isinstance(op, dict):
                            query_ops.append(op)
                elif isinstance(parsed, dict):
                    if "_name" in parsed:
                        query_ops.append(parsed)
                    else:
                        query_ops.append({
                            "_name": "filter",
                            **parsed
                        })
            except json.JSONDecodeError:
                raise ValueError("The 'query' parameter must be a valid JSON string representing TheHive query operations or filters.")
        if sort:
            direction = "desc" if sort.startswith("-") else "asc"
            field = sort.lstrip("-+")
            query_ops.append({
                "_name": "sort",
                "_fields": [
                    {field: direction}
                ]
            })
        
        return self.query(query_ops, limit=limit)

    def update_case(
        self,
        case_id: str,
        status: Optional[str] = None,
        summary: Optional[str] = None,
        severity: Optional[int] = None
    ) -> Dict[str, Any]:
        payload = {}
        if status is not None:
            payload["status"] = status
        if summary is not None:
            payload["summary"] = summary
        if severity is not None:
            payload["severity"] = severity
            
        return self._patch(f"/api/v1/case/{case_id}", json_data=payload)

    # --- Alert Methods ---
    def create_alert(self, type_: str, source: str, source_ref: str, title: str, description: str, severity: int = 2, tags: Optional[List[str]] = None, tlp: int = 2, pap: int = 2) -> Dict[str, Any]:
        payload = {
            "type": type_,
            "source": source,
            "sourceRef": source_ref,
            "title": title,
            "description": description,
            "severity": severity,
            "tags": tags or [],
            "tlp": tlp,
            "pap": pap
        }
        return self._post("/api/v1/alert", json_data=payload)

    def get_alert(self, alert_id: str) -> Dict[str, Any]:
        return self._get(f"/api/v1/alert/{alert_id}")

    def search_alerts(
        self, 
        title: Optional[str] = None, 
        severity: Optional[int] = None, 
        tags: Optional[List[str]] = None, 
        status: Optional[str] = None, 
        sort: Optional[str] = None,
        created_after: Optional[Any] = None,
        created_before: Optional[Any] = None,
        query: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        query_ops = [{"_name": "listAlert"}]
        
        if title:
            query_ops.append({
                "_name": "filter",
                "_like": {
                    "_field": "title",
                    "_value": title
                }
            })
        if severity is not None:
            query_ops.append({
                "_name": "filter",
                "_eq": {
                    "_field": "severity",
                    "_value": severity
                }
            })
        if status:
            query_ops.append({
                "_name": "filter",
                "_eq": {
                    "_field": "status",
                    "_value": status
                }
            })
        if tags:
            for tag in tags:
                query_ops.append({
                    "_name": "filter",
                    "_eq": {
                        "_field": "tags",
                        "_value": tag
                    }
                })
        if created_after is not None:
            ms = parse_date_to_ms(created_after)
            query_ops.append({
                "_name": "filter",
                "_gte": {
                    "_field": "_createdAt",
                    "_value": ms
                }
            })
        if created_before is not None:
            ms = parse_date_to_ms(created_before)
            query_ops.append({
                "_name": "filter",
                "_lte": {
                    "_field": "_createdAt",
                    "_value": ms
                }
            })
        if query:
            import json
            try:
                parsed = json.loads(query)
                if isinstance(parsed, list):
                    for op in parsed:
                        if isinstance(op, dict):
                            query_ops.append(op)
                elif isinstance(parsed, dict):
                    if "_name" in parsed:
                        query_ops.append(parsed)
                    else:
                        query_ops.append({
                            "_name": "filter",
                            **parsed
                        })
            except json.JSONDecodeError:
                raise ValueError("The 'query' parameter must be a valid JSON string representing TheHive query operations or filters.")
        if sort:
            direction = "desc" if sort.startswith("-") else "asc"
            field = sort.lstrip("-+")
            query_ops.append({
                "_name": "sort",
                "_fields": [
                    {field: direction}
                ]
            })
        
        return self.query(query_ops, limit=limit)

    def update_alert(
        self,
        alert_id: str,
        status: Optional[str] = None,
        summary: Optional[str] = None,
        assignee: Optional[str] = None,
        stage: Optional[str] = None
    ) -> Dict[str, Any]:
        payload = {}
        if status is not None:
            payload["status"] = status
        if summary is not None:
            payload["summary"] = summary
        if assignee is not None:
            payload["assignee"] = assignee
        if stage is not None:
            payload["stage"] = stage
            
        return self._patch(f"/api/v1/alert/{alert_id}", json_data=payload)

    def add_alert_comment(self, alert_id: str, message: str) -> Dict[str, Any]:
        payload = {
            "message": message
        }
        return self._post(f"/api/v1/alert/{alert_id}/comment", json_data=payload)

    # --- Observable Methods ---
    def create_observable(self, case_id: str, data_type: str, data: str, message: Optional[str] = None, tags: Optional[List[str]] = None, tlp: int = 2, pap: int = 2, ioc: bool = False) -> Dict[str, Any]:
        payload = {
            "dataType": data_type,
            "data": data,
            "message": message or "",
            "tags": tags or [],
            "tlp": tlp,
            "pap": pap,
            "ioc": ioc
        }
        return self._post(f"/api/v1/case/{case_id}/observable", json_data=payload)

    def get_case_observables(
        self, 
        case_id: str, 
        sort: Optional[str] = None,
        created_after: Optional[Any] = None,
        created_before: Optional[Any] = None,
        query: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        query_ops = [
            {
                "_name": "getCase",
                "idOrName": case_id
            },
            {
                "_name": "observables"
            }
        ]
        
        if created_after is not None:
            ms = parse_date_to_ms(created_after)
            query_ops.append({
                "_name": "filter",
                "_gte": {
                    "_field": "_createdAt",
                    "_value": ms
                }
            })
        if created_before is not None:
            ms = parse_date_to_ms(created_before)
            query_ops.append({
                "_name": "filter",
                "_lte": {
                    "_field": "_createdAt",
                    "_value": ms
                }
            })
        if query:
            import json
            try:
                parsed = json.loads(query)
                if isinstance(parsed, list):
                    for op in parsed:
                        if isinstance(op, dict):
                            query_ops.append(op)
                elif isinstance(parsed, dict):
                    if "_name" in parsed:
                        query_ops.append(parsed)
                    else:
                        query_ops.append({
                            "_name": "filter",
                            **parsed
                        })
            except json.JSONDecodeError:
                raise ValueError("The 'query' parameter must be a valid JSON string representing TheHive query operations or filters.")
        if sort:
            direction = "desc" if sort.startswith("-") else "asc"
            field = sort.lstrip("-+")
            query_ops.append({
                "_name": "sort",
                "_fields": [
                    {field: direction}
                ]
            })
            
        return self.query(query_ops, limit=limit)

    # --- Task & Log Methods ---
    def create_task(self, case_id: str, title: str, description: Optional[str] = None, group: Optional[str] = None, assignee: Optional[str] = None) -> Dict[str, Any]:
        payload = {
            "title": title
        }
        if description:
            payload["description"] = description
        if group:
            payload["group"] = group
        if assignee:
            payload["assignee"] = assignee
            
        return self._post(f"/api/v1/case/{case_id}/task", json_data=payload)

    def get_case_tasks(
        self, 
        case_id: str, 
        sort: Optional[str] = None,
        created_after: Optional[Any] = None,
        created_before: Optional[Any] = None,
        query: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        query_ops = [
            {
                "_name": "getCase",
                "idOrName": case_id
            },
            {
                "_name": "tasks"
            }
        ]
        
        if created_after is not None:
            ms = parse_date_to_ms(created_after)
            query_ops.append({
                "_name": "filter",
                "_gte": {
                    "_field": "_createdAt",
                    "_value": ms
                }
            })
        if created_before is not None:
            ms = parse_date_to_ms(created_before)
            query_ops.append({
                "_name": "filter",
                "_lte": {
                    "_field": "_createdAt",
                    "_value": ms
                }
            })
        if query:
            import json
            try:
                parsed = json.loads(query)
                if isinstance(parsed, list):
                    for op in parsed:
                        if isinstance(op, dict):
                            query_ops.append(op)
                elif isinstance(parsed, dict):
                    if "_name" in parsed:
                        query_ops.append(parsed)
                    else:
                        query_ops.append({
                            "_name": "filter",
                            **parsed
                        })
            except json.JSONDecodeError:
                raise ValueError("The 'query' parameter must be a valid JSON string representing TheHive query operations or filters.")
        if sort:
            direction = "desc" if sort.startswith("-") else "asc"
            field = sort.lstrip("-+")
            query_ops.append({
                "_name": "sort",
                "_fields": [
                    {field: direction}
                ]
            })
            
        return self.query(query_ops, limit=limit)

    def add_task_log(self, task_id: str, message: str) -> Dict[str, Any]:
        payload = {
            "message": message
        }
        return self._post(f"/api/v1/task/{task_id}/log", json_data=payload)
