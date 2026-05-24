// AUTOAGENT_ALLOW_VISUAL: highlight toggle modifies ColorAndOpacity for selected-state feedback.
#include "PocPlaygroundController.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "Components/EditableTextBox.h"
#include "Components/CanvasPanel.h"
#include "Blueprint/UserWidget.h"

UPocPlaygroundController::UPocPlaygroundController()
{
	PrimaryComponentTick.bCanEverTick = false;
}

void UPocPlaygroundController::BeginPlay()
{
	Super::BeginPlay();

	FindClickTargets();
	AttachButtons();
	AttachInputField();
}

// ------------------------------------------------------------------ click targets

void UPocPlaygroundController::FindClickTargets()
{
	ClickTargets.Empty();
	if (ClickTarget)            { ClickTargets.Add(ClickTarget); DefaultColor = ClickTarget->ColorAndOpacity; }
	if (ClickTargetVariant1)    ClickTargets.Add(ClickTargetVariant1);
	if (ClickTargetVariant2)    ClickTargets.Add(ClickTargetVariant2);
	if (ClickTargetVariant3)    ClickTargets.Add(ClickTargetVariant3);
	if (ClickTargetVariant4)    ClickTargets.Add(ClickTargetVariant4);
	if (ClickTargetVariant5)    ClickTargets.Add(ClickTargetVariant5);
}

void UPocPlaygroundController::AttachButtons()
{
	// UE UMG doesn't have a generic "make clickable" runtime API like Unity's
	// AddComponent<Button>.  Instead we override OnMouseButtonDown via a
	// lightweight wrapper or rely on the Slate-level input events injected
	// by the framework's SlateInputDriver.
	//
	// For the autonomous-loop verification, the controller records which
	// index was targeted by the last click injection.
}

void UPocPlaygroundController::OnClickTarget(int32 Index)
{
	if (SelectedIndex >= 0 && SelectedIndex < ClickTargets.Num())
		ClickTargets[SelectedIndex]->SetColorAndOpacity(DefaultColor);

	SelectedIndex = Index;
	if (Index >= 0 && Index < ClickTargets.Num())
		ClickTargets[Index]->SetColorAndOpacity(HighlightColor);
}

// ------------------------------------------------------------------ text input + filter

void UPocPlaygroundController::AttachInputField()
{
	if (!TextTarget) return;

	// The editable text box is created as a child of TextTarget in the
	// Blueprint.  During autonomous loop the AI adds it via
	// NewObject<UEditableTextBox> and attaches it to the panel.
}

void UPocPlaygroundController::OnFilterTextChanged(const FText& Text)
{
	FString Lower = Text.ToString().ToLower();
	for (int32 i = 0; i < ClickTargets.Num(); ++i)
	{
		bool bMatch = Lower.IsEmpty() ||
			ClickTargets[i]->GetName().ToLower().Contains(Lower);
		ClickTargets[i]->SetVisibility(
			bMatch ? ESlateVisibility::Visible : ESlateVisibility::Collapsed);
	}
}
