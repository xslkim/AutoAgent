#pragma once

#include "Blueprint/UserWidget.h"
#include "Components/Button.h"
#include "Components/EditableTextBox.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "LoginUserWidget.generated.h"

/**
 * Visual + interactive skeleton for the AutoAgent login fixture.
 *
 * Widget types
 * ------------
 *  Visual panels  — UImage    (no interaction; position / color are read-only)
 *  Text labels    — UTextBlock (read-only display)
 *  Text inputs    — UEditableTextBox  (AutoAgent send_text target)
 *  Login button   — UButton           (AutoAgent click target → OnClicked delegate)
 *
 * All UPROPERTY names are kept identical to the Unity fixture's stable-ID
 * registry so that the same login.yaml DSL drives both engines.
 */
UCLASS()
class AUTOAGENTTEST_API ULoginUserWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	// ---- visual panels -------------------------------------------------------

	UPROPERTY(meta = (BindWidget, AutoAgentId = "login_panel", AutoAgentLogicalRole = "image_only"))
	UImage* LoginPanel;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "welcome_panel", AutoAgentLogicalRole = "image_only"))
	UImage* WelcomePanel;

	// ---- text inputs (AutoAgent send_text targets) ---------------------------

	UPROPERTY(meta = (BindWidget, AutoAgentId = "account_input_bg", AutoAgentLogicalRole = "input"))
	UEditableTextBox* AccountInputBg;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "password_input_bg", AutoAgentLogicalRole = "input"))
	UEditableTextBox* PasswordInputBg;

	// ---- login button (AutoAgent click target) --------------------------------

	UPROPERTY(meta = (BindWidget, AutoAgentId = "login_button_bg", AutoAgentLogicalRole = "button"))
	UButton* LoginButtonBg;

	// ---- text labels (read-only display) ------------------------------------

	UPROPERTY(meta = (BindWidget, AutoAgentId = "login_button_label", AutoAgentLogicalRole = "text_display"))
	UTextBlock* LoginButtonLabel;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "error_label", AutoAgentLogicalRole = "text_display"))
	UTextBlock* ErrorLabel;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "welcome_text", AutoAgentLogicalRole = "text_display"))
	UTextBlock* WelcomeText;
};
