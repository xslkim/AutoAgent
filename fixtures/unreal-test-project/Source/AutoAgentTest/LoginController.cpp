// AUTOAGENT_ALLOW_VISUAL: login-flow-state-machine
#include "LoginController.h"
#include "Blueprint/UserWidget.h"
#include "Components/TextBlock.h"
#include "Engine/World.h"
#include "UObject/UObjectIterator.h"

// ---------------------------------------------------------------------------

ULoginController::ULoginController()
{
	PrimaryComponentTick.bCanEverTick = false;
}

// ---------------------------------------------------------------------------
// BeginPlay — locate the widget that the GameMode already added to viewport
// ---------------------------------------------------------------------------

void ULoginController::BeginPlay()
{
	Super::BeginPlay();

	// The LoginMap's GameMode creates ULoginUserWidget and adds it to the
	// viewport in its own BeginPlay.  We find it via UObjectIterator so the
	// controller doesn't need a hard blueprint reference.
	for (TObjectIterator<ULoginUserWidget> It; It; ++It)
	{
		if (IsValid(*It) && (*It)->GetWorld() == GetWorld() && (*It)->IsInViewport())
		{
			LoginWidget = *It;
			break;
		}
	}

	MockApi = NewObject<UMockApi>(this);
	StartAsync();
}

// ---------------------------------------------------------------------------
// StartAsync — wire button delegate and set initial visibility
// ---------------------------------------------------------------------------

void ULoginController::StartAsync()
{
	if (!LoginWidget)
	{
		UE_LOG(LogTemp, Warning, TEXT("[AutoAgent] ULoginController: widget not found — "
									  "ensure the GameMode creates ULoginUserWidget before "
									  "this component's BeginPlay."));
		return;
	}

	// Wire the login button.
	if (LoginWidget->LoginButtonBg)
	{
		LoginWidget->LoginButtonBg->OnClicked.AddDynamic(
			this, &ULoginController::OnLoginClicked);
	}

	// Initial state: welcome_panel and error_label are hidden.
	if (LoginWidget->WelcomePanel)
	{
		LoginWidget->WelcomePanel->SetVisibility(ESlateVisibility::Collapsed);
	}
	if (LoginWidget->WelcomeText)
	{
		LoginWidget->WelcomeText->SetVisibility(ESlateVisibility::Collapsed);
	}
	if (LoginWidget->ErrorLabel)
	{
		LoginWidget->ErrorLabel->SetVisibility(ESlateVisibility::Collapsed);
	}

	UE_LOG(LogTemp, Log, TEXT("[AutoAgent] ULoginController ready."));
}

// ---------------------------------------------------------------------------
// OnLoginClicked — validate credentials and update panel visibility
// ---------------------------------------------------------------------------

void ULoginController::OnLoginClicked()
{
	if (!LoginWidget || !MockApi)
	{
		return;
	}

	// Read credentials from the EditableTextBox widgets.
	const FString Username = LoginWidget->AccountInputBg
								 ? LoginWidget->AccountInputBg->GetText().ToString()
								 : FString();
	const FString Password = LoginWidget->PasswordInputBg
								 ? LoginWidget->PasswordInputBg->GetText().ToString()
								 : FString();

	const FString Result = MockApi->Post(Username, Password);

	if (Result == TEXT("ok"))
	{
		// Hide login panel, reveal welcome panel.
		if (LoginWidget->LoginPanel)
		{
			LoginWidget->LoginPanel->SetVisibility(ESlateVisibility::Collapsed);
		}
		if (LoginWidget->WelcomePanel)
		{
			LoginWidget->WelcomePanel->SetVisibility(ESlateVisibility::Visible);
		}
		if (LoginWidget->WelcomeText)
		{
			LoginWidget->WelcomeText->SetVisibility(ESlateVisibility::Visible);
		}
		if (LoginWidget->ErrorLabel)
		{
			LoginWidget->ErrorLabel->SetVisibility(ESlateVisibility::Collapsed);
		}
	}
	else
	{
		// Show error label.
		if (LoginWidget->ErrorLabel)
		{
			LoginWidget->ErrorLabel->SetText(
				FText::FromString(TEXT("Invalid credentials")));
			LoginWidget->ErrorLabel->SetVisibility(ESlateVisibility::Visible);
		}
	}
}
