from pydantic import BaseModel, ValidationError

class M(BaseModel):
    current_count: int | None
    risk_score: float | None

tests = [
    "",
    " ",
    "NULL",
    "None",
    "12.0",
    "12.5",
    "NaN",
    "jpype.java.lang.Object@12345"
]

for val in tests:
    try:
        M.model_validate({"current_count": val, "risk_score": val})
    except ValidationError as e:
        print(f"Value '{val}' failed:")
        for err in e.errors():
            print(f" - {err['loc'][0]}: {err['msg']}")
