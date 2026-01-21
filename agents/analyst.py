"""
Analyst Agent

Responsibility:
- Convert natural language questions into executable SQL
- Understand the FMCG distribution schema
- Apply business glossary translations
- Format output for downstream consumption

Explicitly NOT responsible for:
- Interpreting results (Strategist's job)
- Making recommendations (Strategist's job)
- Crafting messages (Copywriter's job)
- Direct data access (uses DuckDB through workflow)

Personality:
- "Data Architect" - methodical, precise, literal
- Never invents numbers - only returns what DB contains
- Explains WHY certain joins/filters are needed
- Cites schema definitions in reasoning

Key Design Decisions:
1. SELECT only - never UPDATE/DELETE/DROP
2. VIEW-FIRST: Always prefer views over base tables
3. Always includes retailer_id for traceability
4. Limits results to 50 rows to prevent token overflow
5. Uses CTEs for complex multi-step logic

Error Taxonomy:
- SQL_ERROR: Syntax/execution error → RETRY
- VALIDATION_ERROR: Failed safety checks → RETRY with guidance
- EMPTY_RESULT: Valid SQL, zero rows → VALID ANSWER (no retry)
- VIEW_VIOLATION: Query bypasses views → RETRY with view enforcement

Error Handling:
- Returns {success: False, error: "...", error_type: "..."} on failure
- Self-corrects up to 2 times before giving up
- Empty results are NOT errors (legitimate answer)

Usage:
    from agents.analyst import AnalystAgent
    analyst = AnalystAgent(llm=llm, db_connection=conn)
    result = analyst.generate_query("Show me retailers at churn risk")
"""

import re
import time
from typing import Any, Dict, Optional, List
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage
import pandas as pd

from config.prompts import ANALYST_SYSTEM_PROMPT, ANALYST_RETRY_PROMPT


class AnalystAgent:
    """
    Natural Language to SQL translation agent.
    
    The Analyst is the "eyes" of the system - it retrieves data
    but never interprets it.
    
    Key Features:
    - View-first querying (enforces business logic boundaries)
    - Error taxonomy (distinguishes retry-able vs valid empty results)
    - Row capping (prevents context overflow)
    """
    
    # Allowed views (source of truth)
    ALLOWED_VIEWS = {
        'v_churn_candidates',
        'v_retailer_performance', 
        'v_retailer_categories'
    }
    
    # Base tables (only allowed in JOINs with views)
    BASE_TABLES = {
        'retailers',
        'products',
        'transactions',
        'visits',
        'category_affinities'
    }
    
    # Dangerous patterns (block these)
    BLOCKED_PATTERNS = [
        r'\bDROP\b',
        r'\bDELETE\b',
        r'\bUPDATE\b',
        r'\bINSERT\b',
        r'\bTRUNCATE\b',
        r'\bALTER\b',
        r'\bCREATE\b',
        r'\bGRANT\b',
        r'\bREVOKE\b',
        r'--',  # SQL comments (potential injection)
        r'/\*',  # Block comments
        r'\bground_truth\b',  # Never expose ground truth
    ]
    
    # Maximum rows to return
    MAX_ROWS = 50
    
    # Maximum retries
    MAX_RETRIES = 2
    
    def __init__(self, llm: BaseChatModel, db_connection: Any):
        """
        Initialize the Analyst Agent.
        
        Args:
            llm: LangChain chat model (GPT-4-turbo recommended)
            db_connection: DuckDB connection object
        """
        self.llm = llm
        self.db = db_connection
    
    def generate_query(
        self, 
        question: str,
        retry_context: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Convert natural language to SQL and execute.
        
        Error Taxonomy:
        - SQL_ERROR: Query failed to execute → triggers retry
        - VALIDATION_ERROR: Query failed safety checks → triggers retry
        - EMPTY_RESULT: Query succeeded, zero rows → VALID (no retry)
        
        Args:
            question: User's natural language question
            retry_context: Optional dict with {error, sql} for retry attempts
            
        Returns:
            Dict with keys:
                - success: bool
                - sql: generated SQL query
                - view_used: which view was queried (or None)
                - results: pandas DataFrame (if success)
                - result_metadata: {row_count, execution_time_ms, is_empty}
                - error: error message (if failure)
                - error_type: SQL_ERROR | VALIDATION_ERROR | EMPTY_RESULT
        """
        start_time = time.time()
        
        # Step 1: Generate SQL via LLM
        try:
            if retry_context:
                # Retry with error context
                prompt = ANALYST_RETRY_PROMPT.format(
                    error=retry_context['error'],
                    sql=retry_context['sql']
                )
                messages = [
                    SystemMessage(content=ANALYST_SYSTEM_PROMPT),
                    HumanMessage(content=f"Original question: {question}\n\n{prompt}")
                ]
            else:
                messages = [
                    SystemMessage(content=ANALYST_SYSTEM_PROMPT),
                    HumanMessage(content=question)
                ]
            
            response = self.llm.invoke(messages)
            sql = self._clean_sql(response.content)
            
        except Exception as e:
            return {
                'success': False,
                'sql': None,
                'view_used': None,
                'results': None,
                'result_metadata': None,
                'error': f"LLM generation failed: {str(e)}",
                'error_type': 'SQL_ERROR'
            }
        
        # Step 2: Validate SQL
        validation = self.validate_sql(sql)
        if not validation['valid']:
            return {
                'success': False,
                'sql': sql,
                'view_used': None,
                'results': None,
                'result_metadata': None,
                'error': validation['reason'],
                'error_type': 'VALIDATION_ERROR'
            }
        
        # Step 3: Execute SQL
        try:
            result = self.db.execute(sql)
            df = result.fetchdf()
            execution_time_ms = (time.time() - start_time) * 1000
            
            # Cap rows if needed
            row_count = len(df)
            if row_count > self.MAX_ROWS:
                df = df.head(self.MAX_ROWS)
            
            # Detect which view was used
            view_used = self._detect_view_used(sql)
            
            # Build result metadata
            result_metadata = {
                'row_count': row_count,
                'execution_time_ms': round(execution_time_ms, 2),
                'is_empty': row_count == 0,
                'was_capped': row_count > self.MAX_ROWS
            }
            
            # IMPORTANT: Empty result is a VALID answer, not an error
            return {
                'success': True,
                'sql': sql,
                'view_used': view_used,
                'results': df,
                'result_metadata': result_metadata,
                'error': None,
                'error_type': 'EMPTY_RESULT' if row_count == 0 else None
            }
            
        except Exception as e:
            return {
                'success': False,
                'sql': sql,
                'view_used': None,
                'results': None,
                'result_metadata': None,
                'error': f"SQL execution failed: {str(e)}",
                'error_type': 'SQL_ERROR'
            }
    
    def validate_sql(self, sql: str) -> Dict[str, Any]:
        """
        Validate SQL for safety and view-first enforcement.
        
        Checks:
        1. No dangerous operations (DROP, DELETE, etc.)
        2. FROM clause must reference a view (not just base tables)
        3. No access to ground_truth table
        4. Base tables only allowed in JOINs when a view is the primary source
        
        Args:
            sql: SQL query to validate
            
        Returns:
            {valid: bool, reason: str or None}
        """
        sql_upper = sql.upper()
        sql_lower = sql.lower()
        
        # Check 1: Must be SELECT or WITH (for CTEs)
        sql_trimmed = sql_upper.strip()
        if not (sql_trimmed.startswith('SELECT') or sql_trimmed.startswith('WITH')):
            return {
                'valid': False,
                'reason': 'Query must start with SELECT or WITH (for CTEs)'
            }
        
        # Check 2: Block dangerous patterns
        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, sql, re.IGNORECASE):
                return {
                    'valid': False,
                    'reason': f'Blocked pattern detected: {pattern}'
                }
        
        # Check 3: View-first enforcement - FROM clause MUST contain a view
        # This prevents sneaky JOINs like: SELECT r.* FROM retailers r JOIN transactions t ON ...
        # Exception: category_affinities is allowed standalone (it's config data)
        
        # Extract the FROM clause primary source
        # Use case-insensitive search for FROM followed by view name
        from_view_match = re.search(r'FROM\s+(v_\w+)', sql, re.IGNORECASE)
        has_view_in_from = from_view_match is not None
        
        # Check if only using category_affinities (allowed)
        is_category_affinity_only = (
            'category_affinities' in sql_lower and 
            not any(t in sql_lower for t in ['retailers', 'transactions', 'products', 'visits'])
        )
        
        if not has_view_in_from and not is_category_affinity_only:
            # Check if they're using a view somewhere (maybe in a CTE or subquery)
            has_view_anywhere = any(view in sql_lower for view in self.ALLOWED_VIEWS)
            
            if not has_view_anywhere:
                return {
                    'valid': False,
                    'reason': 'FROM clause must reference a view (v_churn_candidates, v_retailer_performance, or v_retailer_categories). Views contain pre-calculated business logic.',
                    'error_type': 'VIEW_VIOLATION'
                }
            elif not has_view_in_from:
                # View is somewhere but not in main FROM - check if it's valid
                # CTE (WITH clause) with view is okay
                has_cte = re.search(r'\bWITH\b', sql_upper) is not None
                # Subquery with view is okay
                has_subquery_view = re.search(r'\(\s*SELECT[^)]*FROM\s+v_\w+', sql, re.IGNORECASE) is not None
                
                if has_cte or has_subquery_view:
                    # View is in CTE or subquery - that's acceptable
                    pass
                else:
                    return {
                        'valid': False,
                        'reason': 'Primary FROM clause must use a view. Base tables are only allowed in JOINs when a view is the main data source.',
                        'error_type': 'VIEW_VIOLATION'
                    }
        
        return {'valid': True, 'reason': None}
    
    def _clean_sql(self, raw_response: str) -> str:
        """
        Extract clean SQL from LLM response.
        
        Handles:
        - Markdown code blocks
        - Extra whitespace
        - Common LLM preambles
        """
        sql = raw_response.strip()
        
        # Remove markdown code blocks
        if '```sql' in sql:
            sql = sql.split('```sql')[1].split('```')[0]
        elif '```' in sql:
            sql = sql.split('```')[1].split('```')[0]
        
        # Remove common preambles
        preambles = [
            'Here is the SQL query:',
            'Here\'s the SQL:',
            'SQL:',
        ]
        for preamble in preambles:
            if sql.lower().startswith(preamble.lower()):
                sql = sql[len(preamble):]
        
        return sql.strip()
    
    def _detect_view_used(self, sql: str) -> Optional[str]:
        """
        Detect which view is the primary data source.
        
        Parses FROM and JOIN clauses to find views.
        Does NOT scan entire SQL to avoid false positives from:
        - Comments mentioning views
        - String literals containing view names
        - Column aliases that happen to match view names
        
        Returns the first view found in FROM/JOIN, or None if no view used.
        """
        # First, try to find view in FROM clause (primary source)
        from_match = re.search(r'FROM\s+(v_\w+)', sql, re.IGNORECASE)
        if from_match:
            view_name = from_match.group(1).lower()
            if view_name in self.ALLOWED_VIEWS:
                return view_name
        
        # Then check JOIN clauses
        join_matches = re.findall(r'JOIN\s+(v_\w+)', sql, re.IGNORECASE)
        for view_name in join_matches:
            view_name_lower = view_name.lower()
            if view_name_lower in self.ALLOWED_VIEWS:
                return view_name_lower
        
        # Finally, check for views in subqueries (FROM clause in parentheses)
        subquery_from = re.findall(r'\(\s*SELECT.*?FROM\s+(v_\w+)', sql, re.IGNORECASE | re.DOTALL)
        for view_name in subquery_from:
            view_name_lower = view_name.lower()
            if view_name_lower in self.ALLOWED_VIEWS:
                return view_name_lower
        
        # Check CTEs (WITH clause)
        cte_from = re.findall(r'AS\s*\(\s*SELECT.*?FROM\s+(v_\w+)', sql, re.IGNORECASE | re.DOTALL)
        for view_name in cte_from:
            view_name_lower = view_name.lower()
            if view_name_lower in self.ALLOWED_VIEWS:
                return view_name_lower
        
        return None
    
    def _only_uses_base_tables(self, sql: str) -> bool:
        """
        Check if query only references base tables (no views).
        
        Returns True if no views are found in the query.
        """
        sql_lower = sql.lower()
        
        # Check if any view is used
        for view in self.ALLOWED_VIEWS:
            if view in sql_lower:
                return False
        
        # Check if any base table is used
        for table in self.BASE_TABLES:
            if re.search(rf'\b{table}\b', sql_lower):
                return True
        
        return False
    
    def get_schema_context(self) -> str:
        """
        Return the schema context for debugging/display.
        
        Useful for UI to show what the analyst knows about.
        """
        from config.prompts import SCHEMA_CONTEXT
        return SCHEMA_CONTEXT

