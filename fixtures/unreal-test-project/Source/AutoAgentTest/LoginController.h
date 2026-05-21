// AUTOAGENT_ALLOW_VISUAL: login-flow-state-machine
//
// ULoginController — wires LoginUserWidget interactivity for the AutoAgent
// login fixture (TASK-0209).
//
// Responsibilities
// ----------------
//  • Locate the ULoginUserWidget on BeginPlay and validate all BindWidget refs.
//  • Wire UButton::OnClicked for login_button_bg.
//  • On button press: read credentials → call UMockApi::Post() → update widget
//    visibility to reflect auth result (login_panel ↔ welcome_panel).
//
// The AUTOAGENT_ALLOW_VISUAL exemption above is intentional: state transitions
// (login panel → welcome panel) are UX behaviour, not AI-initiated visual
// mutations, and must therefore be permitted.

#pragma once

#include "Components/ActorComponent.h"
#include "LoginUserWidget.h"
#include "MockApi.h"
#include "LoginController.generated.h"

/**
 * Actor Component that drives the login fixture widget.
 *
 * Place this component on the LoginMap's GameMode Actor (or on a dedicated
 * ALoginFlowActor spawned by the GameMode).  Assign the LoginWidget reference
 * in BeginPlay via CreateWidget, then call StartAsync().
 */
UCLASS(ClassGroup = AutoAgent, meta = (BlueprintSpawnableComponent))
class AUTOAGENTTEST_API ULoginController : public UActorComponent
{
	GENERATED_BODY()

public:
	ULoginController();

	/**
	 * Wire the widget and mock API.  Must be called after the widget is
	 * created and added to viewport (called automatically from BeginPlay).
	 */
	UFUNCTION(BlueprintCallable, Category = "AutoAgent|Login")
	void StartAsync();

	/** Expose the widget reference for test assertions. */
	UFUNCTION(BlueprintCallable, Category = "AutoAgent|Login")
	ULoginUserWidget* GetLoginWidget() const { return LoginWidget; }

	/** Expose the mock API for test assertions. */
	UFUNCTION(BlueprintCallable, Category = "AutoAgent|Login")
	UMockApi* GetMockApi() const { return MockApi; }

protected:
	virtual void BeginPlay() override;

private:
	/** Reference to the LoginUserWidget created by BeginPlay. */
	UPROPERTY()
	ULoginUserWidget* LoginWidget = nullptr;

	/** In-process mock API client — no real HTTP required. */
	UPROPERTY()
	UMockApi* MockApi = nullptr;

	/** Called when the user clicks login_button_bg. */
	UFUNCTION()
	void OnLoginClicked();
};
