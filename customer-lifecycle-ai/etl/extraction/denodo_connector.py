import os
import logging
import socket
from collections.abc import Iterator
from typing import Any

from sqlalchemy.sql import Select

logger = logging.getLogger("etl.extraction.denodo")

try:
    import jaydebeapi
except ImportError:
    jaydebeapi = None

class DenodoStreamingExtractor:
    """Streams data from Denodo via JDBC and jaydebeapi."""

    def __init__(
        self,
        username: str,
        password: str,
        host: str,
        port: int,
        database: str,
        java_home: str,
        cacerts: str,
        path_jar: str,
        batch_size: int = 10000,
    ):
        if jaydebeapi is None:
            raise ImportError("jaydebeapi is required for Denodo extraction. 'pip install jaydebeapi JPype1'")

        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.database = database
        self.java_home = java_home
        self.cacerts = cacerts
        self.path_jar = path_jar
        self.batch_size = max(batch_size, 100)

        if java_home:
            os.environ["JAVA_HOME"] = java_home
        elif "JAVA_HOME" not in os.environ:
            raise EnvironmentError("JAVA_HOME must be set.")

    def stream(self, query: Select) -> Iterator[list[dict[str, Any]]]:
        """Compile the SQLAlchemy query to string, execute via JDBC, and yield chunks."""
        from sqlalchemy.dialects import postgresql

        compiled_query = str(query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True}
        ))
        logger.info(f"Denodo compiled query:\n{compiled_query}")

        conn_url = f"jdbc:vdb://{self.host}:{self.port}/{self.database}?sslTrustServerCertificate=true"

        try:
            import jpype

            # ---- STEP 1: Start JVM ----
            if self.java_home:
                cleaned_jh = self.java_home.replace('"', '').replace('\\', '/')
                os.environ["PATH"] = cleaned_jh + "/bin;" + os.environ.get("PATH", "")
                jvm_path = cleaned_jh + "/bin/server/jvm.dll"
                if not jpype.isJVMStarted():
                    logger.info(f"[STEP 1/5] Starting JVM at: {jvm_path}")
                    jpype.startJVM(jvm_path, classpath=[self.path_jar])
                    logger.info("[STEP 1/5] JVM started successfully.")
                else:
                    logger.info("[STEP 1/5] JVM already running — skipped.")
            else:
                if not jpype.isJVMStarted():
                    logger.info(f"[STEP 1/5] Starting default JVM with jar: {self.path_jar}")
                    jpype.startJVM(jpype.getDefaultJVMPath(), classpath=[self.path_jar])
                    logger.info("[STEP 1/5] JVM started successfully.")
                else:
                    logger.info("[STEP 1/5] JVM already running — skipped.")

            # ---- STEP 2: Network reachability check ----
            logger.info(f"[STEP 2/5] Checking network reachability to {self.host}:{self.port} ...")
            try:
                sock = socket.create_connection((self.host, self.port), timeout=10)
                sock.close()
                logger.info(f"[STEP 2/5] Network check PASSED — {self.host}:{self.port} is reachable.")
            except (socket.timeout, OSError) as net_err:
                logger.error(
                    f"[STEP 2/5] NETWORK UNREACHABLE: Cannot reach Denodo at "
                    f"{self.host}:{self.port}. Check VPN/firewall/DNS. Error: {net_err}"
                )
                raise ConnectionError(
                    f"Cannot reach Denodo at {self.host}:{self.port} — {net_err}"
                ) from net_err

            # ---- STEP 3: Open JDBC connection ----
            logger.info(f"[STEP 3/5] Opening JDBC connection to {conn_url} ...")
            conn = jaydebeapi.connect(
                "com.denodo.vdp.jdbc.Driver",
                conn_url,
                [self.username, self.password]
            )
            logger.info("[STEP 3/5] JDBC connection established successfully.")

            # ---- STEP 4: Execute query ----
            cursor = conn.cursor()
            logger.info("[STEP 4/5] Executing query against Denodo ...")
            cursor.execute(compiled_query)
            logger.info("[STEP 4/5] Query executed successfully.")

            # ---- STEP 5: Fetch results ----
            columns = [desc[0] for desc in cursor.description]
            logger.info(f"[STEP 5/5] Fetching results. Columns ({len(columns)}): {columns}")

            batch_num = 0
            while True:
                rows = cursor.fetchmany(self.batch_size)
                if not rows:
                    logger.info(f"[STEP 5/5] Fetch complete. Total batches streamed: {batch_num}")
                    break
                batch_num += 1
                logger.info(f"[STEP 5/5] Fetched batch {batch_num} ({len(rows)} rows)")

                chunk = []
                for row in rows:
                    cleaned_row = []
                    for x in row:
                        if x is None:
                            cleaned_row.append(None)
                        elif type(x) in (int, float, bool):
                            import math
                            if type(x) is float and math.isnan(x):
                                cleaned_row.append(None)
                            else:
                                cleaned_row.append(x)
                        else:
                            s = str(x).strip()
                            if s == "" or s.upper() in ("NULL", "NAN", "NONE"):
                                cleaned_row.append(None)
                            else:
                                cleaned_row.append(s)
                    chunk.append(dict(zip(columns, cleaned_row)))
                yield chunk

        except Exception as e:
            logger.error(f"Denodo extraction error: {e}")
            raise
        finally:
            try:
                cursor.close()
            except:
                pass
            try:
                conn.close()
            except:
                pass
