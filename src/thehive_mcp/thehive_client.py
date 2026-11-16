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

ERROR_BODY_MAX = 500


class TheHiveHTTPError(RuntimeError):
    """Non-2xx answer from TheHive. The message is readable by the agent:
    '<METHOD> <path> -> HTTP <code> : <truncated body>'."""

    def __init__(self, method: str, path: str, status_code: int, body: str):
        self.method = method
        self.path = path
        self.status_code = status_code
        self.body = body
        super().__init__(f"{method} {path} -> HTTP {status_code} : {body}")


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

    def _request(self, method: str, path: str, json_data: Any = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(method, url, headers=self.headers, json=json_data, verify=self.verify_ssl)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error on {method} {path}: {e}")
            raise RuntimeError(f"{method} {path} -> request failed : {e}")
        if not response.ok:
            # Note: a non-2xx Response is falsy, never test it with `if response`.
            body = (response.text or "")[:ERROR_BODY_MAX]
            logger.error(f"HTTP error on {method} {path}: {response.status_code} - {body}")
            raise TheHiveHTTPError(method, path, response.status_code, body)
        # Some endpoints return 204 No Content or an empty body
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError:
            return {}

    def _get(self, path: str) -> Any:
        return self._request("GET", path)

    def _post(self, path: str, json_data: Any = None) -> Any:
        return self._request("POST", path, json_data)

    def _patch(self, path: str, json_data: Any = None) -> Any:
        return self._request("PATCH", path, json_data)

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
        limit: int = 10,
        open_only: bool = False
    ) -> List[Dict[str, Any]]:
        query_ops = [{"_name": "listCase"}]

        if open_only:
            query_ops.append({
                "_name": "filter",
                "_not": {"_eq": {"_field": "stage", "_value": "Closed"}}
            })
        
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
        severity: Optional[int] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        payload = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if tags is not None:
            payload["tags"] = tags
        if status is not None:
            payload["status"] = status
        if summary is not None:
            payload["summary"] = summary
        if severity is not None:
            payload["severity"] = severity
            
        return self._patch(f"/api/v1/case/{case_id}", json_data=payload)

    def case_summary(self, case: Dict[str, Any]) -> Dict[str, Any]:
        case_id = case.get("_id") or case.get("id")
        return {
            "case_id": case_id,
            "number": case.get("number") or case.get("caseId"),
            "title": case.get("title"),
            "status": case.get("status"),
            "stage": case.get("stage"),
            "severity": case.get("severity"),
            "tags": case.get("tags", []),
            "url": f"{self.base_url}/cases/{case_id}/details",
        }

    def find_case_template(self, name: str) -> Optional[Dict[str, Any]]:
        results = self.query([
            {"_name": "listCaseTemplate"},
            {"_name": "filter", "_eq": {"_field": "name", "_value": name}},
        ], limit=1)
        return results[0] if results else None

    def create_case_from_alert(
        self,
        alert_id: str,
        case_template: Optional[str] = None,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Promote an alert into a case (UI "Create case from alert")."""
        alert = self.get_alert(alert_id)
        if alert.get("caseId"):
            raise ValueError(
                f"Alert {alert_id} is already linked to case {alert['caseId']}: no case created. "
                "Use merge_alerts_into_case to attach other alerts to that case."
            )
        if case_template and not self.find_case_template(case_template):
            raise ValueError(f"Unknown case template '{case_template}': no case created.")

        payload = {"caseTemplate": case_template} if case_template else {}
        try:
            case = self._post(f"/api/v1/alert/{alert_id}/case", json_data=payload)
        except TheHiveHTTPError as e:
            if e.status_code not in (404, 405):
                raise
            # Route missing on this TheHive version: fall back to the v0 API.
            case = self._post(f"/api/alert/{alert_id}/createCase", json_data=payload)

        result = self.case_summary(case)
        patch_payload: Dict[str, Any] = {}
        if title:
            patch_payload["title"] = title
        if tags:
            current = list(case.get("tags") or [])
            merged = current + [t for t in tags if t not in current]
            if merged != current:
                patch_payload["tags"] = merged
        if patch_payload:
            try:
                self._patch(f"/api/v1/case/{result['case_id']}", json_data=patch_payload)
                result.update(patch_payload)
            except RuntimeError as e:
                result["warning"] = f"Case created but title/tags update failed: {e}"
        return result

    def merge_alerts_into_case(self, alert_ids: List[str], case_id: str) -> Dict[str, Any]:
        """Attach alerts to an existing case (UI "Merge into case"), one by one."""
        if not alert_ids:
            raise ValueError("alert_ids must contain at least one alert ID.")
        case = self.get_case(case_id)
        target_id = case.get("_id") or case_id
        merged: List[str] = []
        failed: List[Dict[str, str]] = []
        for alert_id in alert_ids:
            try:
                alert = self.get_alert(alert_id)
                linked = alert.get("caseId")
                if linked and linked != target_id:
                    failed.append({"alert_id": alert_id, "error": f"Alert already linked to another case ({linked})."})
                    continue
                if not linked:
                    self._post(f"/api/v1/alert/{alert_id}/merge/{target_id}")
                merged.append(alert_id)
            except (RuntimeError, ValueError) as e:
                failed.append({"alert_id": alert_id, "error": str(e)})
        return {"case_id": target_id, "merged": merged, "failed": failed}

    def add_case_comment(self, case_id: str, message: str) -> Dict[str, Any]:
        result = self._post(f"/api/v1/case/{case_id}/comment", json_data={"message": message})
        return {"case_id": case_id, "comment_id": result.get("_id"), "status": "ok"}

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

