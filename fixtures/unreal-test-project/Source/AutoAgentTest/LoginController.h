// AUTOAGENT_ALLOW_VISUAL: login-flow-state-machine
//
// ULoginController — wires ULoginUserWidget for the AutoAgent login fixture.
//
// Responsibilities
// ----------------
//  • On BeginPlay: find the ULoginUserWidget in the viewport and call StartAsync().
//  • StartAsync(): wire LoginButtonBg::OnClicked, set initial panel visibility.
//  • OnLoginClicked(): read credentials → UMockApi::Post() → toggle panels.
//
// The AUTOAGENT_ALLOW_VISUAL exemption is intentional: panel visibility changes
// (login_panel ↔ welcome_panel) reflect authentication state, not AI-initiated
// visual mutations; they are permitted under §2.5 of docs/06-visual-regression.md.

#pragma once

#include "Components/ActorComponent.h"
#include "LoginUserWidget.h"
#include "MockApi.h"
#include "LoginController.generated.h"

UCLASS(ClassGroup = AutoAgent, meta = (BlueprintSpawnableComponent))
class AUTOAGENTTEST_API ULoginController : public UActorComponent
{
	GENERATED_BODY()

public:
	ULoginController();

	/**
	 * Wire widget interactivity and set initial panel visibility.
	 * Called automatically from BeginPlay; safe to call again after a widget
	 * hot-swap (e.g., during PIE restart).
	 */
	UFUNCTION(BlueprintCallable, Category = "AutoAgent|Login")
	void StartAsync();

	// Accessors for automation tests.
	UFUNCTION(BlueprintCallable, Category = "AutoAgent|Login")
	ULoginUserWidget* GetLoginWidget() const { return LoginWidget; }

	UFUNCTION(BlueprintCallable, Category = "AutoAgent|Login")
	UMockApi* GetMockApi() const { return MockApi; }

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY()
	ULoginUserWidget* LoginWidget = nullptr;

	UPROPERTY()
	UMockApi* MockApi = nullptr;

	/** Triggered when the agent (or user) clicks login_button_bg. */
	UFUNCTION()
	void OnLoginClicked();
};
