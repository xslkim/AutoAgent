// AUTOAGENT_ALLOW_VISUAL: login-flow-state-machine
//
// Intentional visibility toggles: login_panel ↔ welcome_panel reflect
// authentication state, not AI-driven visual mutations.

#include "LoginController.h"
#include "Blueprint/UserWidget.h"
#include "Components/EditableTextBox.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"

// ---------------------------------------------------------------------------
// Construction
// ---------------------------------------------------------------------------

ULoginController::ULoginController()
{
	PrimaryComponentTick.bCanEverTick = false;
}

// ---------------------------------------------------------------------------
// BeginPlay — create widget + wire interactivity
// ---------------------------------------------------------------------------

void ULoginController::BeginPlay()
{
	Super::BeginPlay();

	// TODO (TASK-0209 autonomous loop): create the LoginUserWidget, add it to
	// viewport, and call StartAsync().
	//
	// Example skeleton:
	//
	//   APlayerController* PC = GetWorld()->GetFirstPlayerController();
	//   if (!PC) return;
	//
	//   LoginWidget = CreateWidget<ULoginUserWidget>(PC,
	//       ULoginUserWidget::StaticClass());
	//   if (!LoginWidget) return;
	//   LoginWidget->AddToViewport();
	//
	//   MockApi = NewObject<UMockApi>(this);
	//   StartAsync();
}

// ---------------------------------------------------------------------------
// StartAsync — wire button and verify preconditions
// ---------------------------------------------------------------------------

void ULoginController::StartAsync()
{
	// TODO (TASK-0209 autonomous loop):
	// 1. Verify LoginWidget is valid and all BindWidget refs are non-null.
	// 2. Wire login_button_bg::OnClicked → OnLoginClicked.
	// 3. Ensure welcome_panel is initially Collapsed.
	//
	// Example skeleton:
	//
	//   if (!LoginWidget || !LoginWidget->LoginButtonBg) return;
	//
	//   LoginWidget->LoginButtonBg->OnClicked.AddDynamic(
	//       this, &ULoginController::OnLoginClicked);
	//
	//   LoginWidget->WelcomePanel->SetVisibility(ESlateVisibility::Collapsed);
}

// ---------------------------------------------------------------------------
// OnLoginClicked — read credentials, call mock API, update visibility
// ---------------------------------------------------------------------------

void ULoginController::OnLoginClicked()
{
	// TODO (TASK-0209 autonomous loop):
	// 1. Read text from account_input_bg and password_input_bg.
	// 2. Call MockApi->Post(Username, Password).
	// 3. On "ok": hide login_panel, show welcome_panel + welcome_text.
	// 4. On "error": show error_label with "Invalid credentials".
	//
	// Example skeleton:
	//
	//   if (!LoginWidget || !MockApi) return;
	//
	//   const FString Username = LoginWidget->AccountInputBg
	//       ? static_cast<UEditableTextBox*>(LoginWidget->AccountInputBg)->GetText().ToString()
	//       : FString();
	//   const FString Password = LoginWidget->PasswordInputBg
	//       ? static_cast<UEditableTextBox*>(LoginWidget->PasswordInputBg)->GetText().ToString()
	//       : FString();
	//
	//   const FString Result = MockApi->Post(Username, Password);
	//   if (Result == TEXT("ok"))
	//   {
	//       LoginWidget->LoginPanel->SetVisibility(ESlateVisibility::Collapsed);
	//       LoginWidget->WelcomePanel->SetVisibility(ESlateVisibility::Visible);
	//       LoginWidget->WelcomeText->SetVisibility(ESlateVisibility::Visible);
	//   }
	//   else
	//   {
	//       LoginWidget->ErrorLabel->SetText(FText::FromString(TEXT("Invalid credentials")));
	//       LoginWidget->ErrorLabel->SetVisibility(ESlateVisibility::Visible);
	//   }
}
