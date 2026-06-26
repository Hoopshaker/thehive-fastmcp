import logging
from typing import List, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
from .thehive_client import TheHiveClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("thehive_mcp")

# Instantiate FastMCP server
mcp = FastMCP("TheHive MCP Server")

# Lazy client instantiation helper to avoid startup errors if env vars are missing
_client = None

def get_client() -> TheHiveClient:
    global _client
    if _client is None:
        try:
            _client = TheHiveClient()
        except ValueError as e:
            logger.error(f"Initialization error: {e}")
            raise RuntimeError(f"Server initialization failed: {e}. Ensure THEHIVE_URL and THEHIVE_API_KEY are configured.")
    return _client

# --- Tools: Cases ---

@mcp.tool()
def get_case(id_or_name: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific case by its ID or case number.
    
    Args:
        id_or_name (str): The unique ID of the case (starts with '~') or the case number.
    """
    client = get_client()
    return client.get_case(id_or_name)

@mcp.tool()
def create_case(
    title: str, 
    description: str, 
    severity: int = 2, 
    tags: Optional[List[str]] = None, 
    tlp: int = 2, 
    pap: int = 2, 
    flag: bool = False
) -> Dict[str, Any]:
    """
    Create a new empty security incident Case in TheHive.
    
    Args:
        title (str): Title of the case.
        description (str): Detailed markdown-supported description of the case.
        severity (int): Severity level: 1 (Low), 2 (Medium), 3 (High), 4 (Critical). Default is 2.
        tags (List[str], optional): List of tags to categorize the case.
        tlp (int): Traffic Light Protocol level: 0 (White), 1 (Green), 2 (Amber), 3 (Amber+Strict), 4 (Red). Default is 2.
        pap (int): Permissible Action Protocol level: 0 (White), 1 (Green), 2 (Amber), 3 (Red). Default is 2.
        flag (bool): Mark the case as flagged/starred. Default is False.
    """
    client = get_client()
    return client.create_case(
        title=title,
        description=description,
        severity=severity,
        tags=tags,
        tlp=tlp,
        pap=pap,
        flag=flag
    )

@mcp.tool()
def search_cases(
    title: Optional[str] = None, 
    severity: Optional[int] = None, 
    tags: Optional[List[str]] = None, 
    status: Optional[str] = None, 
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Search for Cases in TheHive with advanced filtering capabilities.
    
    Args:
        title (str, optional): Substring match on the Case title.
        severity (int, optional): Filter by exact severity level (1 to 4).
        tags (List[str], optional): Filter by tags (requires all tags to match).
        status (str, optional): Filter by status (e.g. 'Open', 'Resolved').
        limit (int): Maximum number of cases to return. Default is 10.
    """
    client = get_client()
    return client.search_cases(
        title=title,
        severity=severity,
        tags=tags,
        status=status,
        limit=limit
    )

# --- Tools: Alerts ---

@mcp.tool()
def get_alert(alert_id: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific alert by its ID.
    
    Args:
        alert_id (str): The unique ID of the alert.
    """
    client = get_client()
    return client.get_alert(alert_id)

@mcp.tool()
def create_alert(
    type_name: str,
    source: str,
    source_ref: str,
    title: str,
    description: str,
    severity: int = 2,
    tags: Optional[List[str]] = None,
    tlp: int = 2,
    pap: int = 2
) -> Dict[str, Any]:
    """
    Create a new Alert in TheHive. Alerts represent potential incidents fetched from SIEMs, emails, etc.
    
    Args:
        type_name (str): Type of the alert (e.g., 'SIEM', 'Phishing', 'EDR').
        source (str): Source/provider of the alert (e.g., 'Splunk', 'Wazuh').
        source_ref (str): Unique reference ID from the source system.
        title (str): Title of the alert.
        description (str): Detailed markdown-supported description.
        severity (int): Severity level: 1 (Low), 2 (Medium), 3 (High), 4 (Critical). Default is 2.
        tags (List[str], optional): List of tags to categorize the alert.
        tlp (int): Traffic Light Protocol level (0 to 4). Default is 2.
        pap (int): Permissible Action Protocol level (0 to 3). Default is 2.
    """
    client = get_client()
    return client.create_alert(
        type_=type_name,
        source=source,
        source_ref=source_ref,
        title=title,
        description=description,
        severity=severity,
        tags=tags,
        tlp=tlp,
        pap=pap
    )

@mcp.tool()
def search_alerts(
    title: Optional[str] = None, 
    severity: Optional[int] = None, 
    tags: Optional[List[str]] = None, 
    status: Optional[str] = None, 
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Search for Alerts in TheHive with advanced filtering.
    
    Args:
        title (str, optional): Substring match on the Alert title.
        severity (int, optional): Filter by exact severity level (1 to 4).
        tags (List[str], optional): Filter by tags (requires all tags to match).
        status (str, optional): Filter by status (e.g. 'New', 'Imported', 'Ignored').
        limit (int): Maximum number of alerts to return. Default is 10.
    """
    client = get_client()
    return client.search_alerts(
        title=title,
        severity=severity,
        tags=tags,
        status=status,
        limit=limit
    )

# --- Tools: Observables ---

@mcp.tool()
def create_observable(
    case_id: str,
    data_type: str,
    data: str,
    message: Optional[str] = None,
    tags: Optional[List[str]] = None,
    tlp: int = 2,
    pap: int = 2,
    ioc: bool = False
) -> Dict[str, Any]:
    """
    Add an Observable (IoC/Indicator of Compromise) to an existing Case.
    
    Args:
        case_id (str): The unique ID of the target Case.
        data_type (str): Type of observable (e.g., 'ip', 'domain', 'hash', 'mail', 'url').
        data (str): The actual observable value (e.g. '192.168.1.1' or 'bad-domain.com').
        message (str, optional): A description or comment regarding this observable.
        tags (List[str], optional): List of tags to add to the observable.
        tlp (int): Traffic Light Protocol level (0 to 4). Default is 2.
        pap (int): Permissible Action Protocol level (0 to 3). Default is 2.
        ioc (bool): Whether to mark this observable as an active Indicator of Compromise. Default is False.
    """
    client = get_client()
    return client.create_observable(
        case_id=case_id,
        data_type=data_type,
        data=data,
        message=message,
        tags=tags,
        tlp=tlp,
        pap=pap,
        ioc=ioc
    )

@mcp.tool()
def get_case_observables(case_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    List all observables associated with a specific Case.
    
    Args:
        case_id (str): The unique ID or name/number of the Case.
        limit (int): Maximum number of observables to return. Default is 50.
    """
    client = get_client()
    return client.get_case_observables(case_id, limit=limit)

# --- Tools: Tasks & Logs ---

@mcp.tool()
def create_task(
    case_id: str,
    title: str,
    description: Optional[str] = None,
    group: Optional[str] = None,
    assignee: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new Task inside an existing Case for tracking investigation steps.
    
    Args:
        case_id (str): The unique ID of the target Case.
        title (str): Title of the task.
        description (str, optional): Detailed explanation of the task.
        group (str, optional): Group category for the task.
        assignee (str, optional): Login/email of the user assigned to this task.
    """
    client = get_client()
    return client.create_task(
        case_id=case_id,
        title=title,
        description=description,
        group=group,
        assignee=assignee
    )

@mcp.tool()
def get_case_tasks(case_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    List all tasks associated with a specific Case.
    
    Args:
        case_id (str): The unique ID or name/number of the Case.
        limit (int): Maximum number of tasks to return. Default is 50.
    """
    client = get_client()
    return client.get_case_tasks(case_id, limit=limit)

@mcp.tool()
def add_task_log(task_id: str, message: str) -> Dict[str, Any]:
    """
    Add a progress log entry (log note) to an existing Task.
    
    Args:
        task_id (str): The unique ID of the Task.
        message (str): Log message (describing progress, results, or notes). Supports markdown.
    """
    client = get_client()
    return client.add_task_log(task_id, message)

def main():
    # Start the FastMCP stdio server
    mcp.run()

if __name__ == "__main__":
    main()
