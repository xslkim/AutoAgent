#include "MockApi.h"

FString UMockApi::Post(const FString& Username, const FString& Password)
{
	bPostCalled = true;
	LastUsername = Username;
	LastPassword = Password;

	// Valid credentials defined by the AutoAgent login task DSL (login_ue.yaml).
	if (Username == TEXT("admin") && Password == TEXT("password"))
	{
		return TEXT("ok");
	}
	return TEXT("error");
}

void UMockApi::Reset()
{
	bPostCalled = false;
	LastUsername.Empty();
	LastPassword.Empty();
}
