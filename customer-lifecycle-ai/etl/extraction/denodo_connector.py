import os
import logging
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
        # Compile query to raw SQL string
        # We use a dummy postgresql dialect to get standard ANSI SQL
        from sqlalchemy.dialects import postgresql
        
        compiled_query = str(query.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True}
        ))
        logger.info(f"Denodo compiled query:\n{compiled_query}")

        conn_url = f"jdbc:vdb://{self.host}:{self.port}/{self.database}?sslTrustServerCertificate=true"

        try:
            logger.info("Connecting to Denodo JDBC...")
            
            import jpype
            if self.java_home:
                # Add bin to path to find sister dlls
                cleaned_jh = self.java_home.replace('"', '').replace('\\', '/')
                os.environ["PATH"] = cleaned_jh + "/bin;" + os.environ.get("PATH", "")
                jvm_path = cleaned_jh + "/bin/server/jvm.dll"
                if not jpype.isJVMStarted():
                    logger.info(f"Starting JVM at {jvm_path} with jar {self.path_jar}")
                    jpype.startJVM(jvm_path, classpath=[self.path_jar])
            else:
                if not jpype.isJVMStarted():
                    logger.info(f"Starting default system JVM with jar {self.path_jar}")
                    jpype.startJVM(jpype.getDefaultJVMPath(), classpath=[self.path_jar])

            conn = jaydebeapi.connect(
                "com.denodo.vdp.jdbc.Driver",
                conn_url,
                [self.username, self.password]
            )
            
            cursor = conn.cursor()
            cursor.execute(compiled_query)
            
            # Get column names
            columns = [desc[0] for desc in cursor.description]
            
            while True:
                rows = cursor.fetchmany(self.batch_size)
                if not rows:
                    break
                    
                chunk = []
                for row in rows:
                    chunk.append(dict(zip(columns, row)))
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
