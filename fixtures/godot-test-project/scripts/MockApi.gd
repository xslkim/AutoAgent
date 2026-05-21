extends RefCounted
## MockApi — stub back-end for the login fixture.
##
## Returns "ok" for admin/password, "error" for everything else.
## Records every call in call_history for test assertions.

const _VALID_CREDENTIALS := {"admin": "password"}

## Ordered list of all login attempts, newest last.
## Each entry is {"username": String, "password": String, "result": String}.
var call_history: Array[Dictionary] = []


## Attempt a login and return "ok" or "error".
func login(username: String, password: String) -> String:
	var result := "error"
	if _VALID_CREDENTIALS.get(username, "") == password:
		result = "ok"
	call_history.append({"username": username, "password": password, "result": result})
	return result


## Reset call history (useful between test runs).
func reset() -> void:
	call_history.clear()
