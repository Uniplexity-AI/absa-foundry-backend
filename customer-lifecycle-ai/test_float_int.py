from pydantic import BaseModel

class M(BaseModel):
    current_count: int | None

try:
    M.model_validate({"current_count": "12.0"})
    print("Parsed 12.0 successfully")
except Exception as e:
    print("Failed on 12.0:", e)

try:
    M.model_validate({"current_count": 12.0})
    print("Parsed float 12.0 successfully")
except Exception as e:
    print("Failed on float 12.0:", e)
