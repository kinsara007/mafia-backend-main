from pydantic import BaseModel, ConfigDict

class UserDTO(BaseModel):
    name:str
    email:str
    password:str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email:str

class LoginDTO(BaseModel):
    email:str
    password:str