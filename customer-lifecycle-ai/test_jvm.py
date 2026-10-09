import jpype
from shared.config.settings import settings

cleaned_path = settings.java_home.replace('"', '').replace('\\', '/')
jvm_dll = cleaned_path + "/bin/server/jvm.dll"

print("Starting JVM from:", jvm_dll)
try:
    jpype.startJVM(jvm_dll, classpath=[settings.denodo_jar_path])
    print("Success! JVM Started.")
except Exception as e:
    print(f"Error starting JVM: {e}")
