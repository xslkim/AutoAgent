#pragma once

#include "Blueprint/UserWidget.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "LoginUserWidget.generated.h"

UCLASS()
class AUTOAGENTTEST_API ULoginUserWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UPROPERTY(meta=(BindWidget, AutoAgentId="login_panel", AutoAgentLogicalRole="image_only"))
	UImage* LoginPanel;

	UPROPERTY(meta=(BindWidget, AutoAgentId="account_input_bg", AutoAgentLogicalRole="input"))
	UImage* AccountInputBg;

	UPROPERTY(meta=(BindWidget, AutoAgentId="account_input_text", AutoAgentLogicalRole="text_display"))
	UTextBlock* AccountInputText;

	UPROPERTY(meta=(BindWidget, AutoAgentId="password_input_bg", AutoAgentLogicalRole="input"))
	UImage* PasswordInputBg;

	UPROPERTY(meta=(BindWidget, AutoAgentId="password_input_text", AutoAgentLogicalRole="text_display"))
	UTextBlock* PasswordInputText;

	UPROPERTY(meta=(BindWidget, AutoAgentId="login_button_bg", AutoAgentLogicalRole="button"))
	UImage* LoginButtonBg;

	UPROPERTY(meta=(BindWidget, AutoAgentId="login_button_label", AutoAgentLogicalRole="text_display"))
	UTextBlock* LoginButtonLabel;

	UPROPERTY(meta=(BindWidget, AutoAgentId="error_label", AutoAgentLogicalRole="text_display"))
	UTextBlock* ErrorLabel;

	UPROPERTY(meta=(BindWidget, AutoAgentId="welcome_panel", AutoAgentLogicalRole="image_only"))
	UImage* WelcomePanel;

	UPROPERTY(meta=(BindWidget, AutoAgentId="welcome_text", AutoAgentLogicalRole="text_display"))
	UTextBlock* WelcomeText;
};
