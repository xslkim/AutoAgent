#pragma once

#include "UObject/Object.h"
#include "MockApi.generated.h"

/**
 * In-process mock HTTP client for the AutoAgent login fixture (TASK-0209).
 *
 * Simulates the backend authentication endpoint without a real network
 * connection.  The login flow is:
 *
 *   Post("admin", "password") → "ok"
 *   Post(<anything else>)     → "error"
 *
 * ULoginController creates one instance of this object in BeginPlay.
 * The autonomous loop (TASK-0209) may extend this class to record call
 * history for assertion in step_assert_api_called.
 */
UCLASS(MinimalAPI, Transient)
class AUTOAGENTTEST_API UMockApi : public UObject
{
	GENERATED_BODY()

public:
	/**
	 * Simulate a POST /login request.
	 *
	 * @param Username  The username entered by the user.
	 * @param Password  The password entered by the user.
	 * @return "ok" if credentials are valid, "error" otherwise.
	 */
	UFUNCTION(BlueprintCallable, Category = "AutoAgent|MockApi")
	FString Post(const FString& Username, const FString& Password);

	/** True if Post() has been called at least once. */
	UFUNCTION(BlueprintCallable, Category = "AutoAgent|MockApi")
	bool WasPostCalled() const { return bPostCalled; }

	/** The last username passed to Post(). */
	UFUNCTION(BlueprintCallable, Category = "AutoAgent|MockApi")
	FString GetLastUsername() const { return LastUsername; }

	/** The last password passed to Post(). */
	UFUNCTION(BlueprintCallable, Category = "AutoAgent|MockApi")
	FString GetLastPassword() const { return LastPassword; }

	/** Reset call history (useful for multi-step test assertions). */
	UFUNCTION(BlueprintCallable, Category = "AutoAgent|MockApi")
	void Reset();

private:
	bool bPostCalled = false;
	FString LastUsername;
	FString LastPassword;
};
