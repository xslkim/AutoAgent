// AUTOAGENT_ALLOW_VISUAL: highlight toggle modifies ColorAndOpacity for selected-state feedback.
#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "PocPlaygroundController.generated.h"

class UImage;
class UTextBlock;
class UEditableTextBox;
class UCanvasPanel;

/**
 * Interactive card-panel controller for the WBP_PocPlayground widget.
 *
 * AI-written by Claude Code during autonomous loop (TASK POC-PLAYGROUND-001).
 */
UCLASS(ClassGroup = (AutoAgent), meta = (BlueprintSpawnableComponent))
class UPocPlaygroundController : public UActorComponent
{
	GENERATED_BODY()

public:
	UPocPlaygroundController();

protected:
	virtual void BeginPlay() override;

	// ---- click targets ----
	UFUNCTION()
	void OnClickTarget(int32 Index);

	// ---- filter ----
	UFUNCTION()
	void OnFilterTextChanged(const FText& Text);

private:
	void FindClickTargets();
	void AttachButtons();
	void AttachInputField();

	// BindWidget properties (matched by AutoAgentId meta in the Blueprint).
	UPROPERTY(meta = (BindWidget, AutoAgentId = "click_target"))
	UImage* ClickTarget;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "click_target_variant_1"))
	UImage* ClickTargetVariant1;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "click_target_variant_2"))
	UImage* ClickTargetVariant2;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "click_target_variant_3"))
	UImage* ClickTargetVariant3;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "click_target_variant_4"))
	UImage* ClickTargetVariant4;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "click_target_variant_5"))
	UImage* ClickTargetVariant5;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "text_target"))
	UImage* TextTarget;

	UPROPERTY(meta = (BindWidget, AutoAgentId = "text_target_text"))
	UTextBlock* TextTargetText;

	TArray<UImage*> ClickTargets;
	int32 SelectedIndex = -1;
	FLinearColor DefaultColor = FLinearColor::White;
	FLinearColor HighlightColor = FLinearColor(1.0f, 0.85f, 0.3f, 1.0f);
};
