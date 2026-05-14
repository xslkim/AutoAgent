#pragma once

#include "Blueprint/UserWidget.h"
#include "Components/CanvasPanel.h"
#include "Components/Image.h"
#include "Components/TextBlock.h"
#include "PocPlaygroundUserWidget.generated.h"

UCLASS()
class AUTOAGENTTEST_API UPocPlaygroundUserWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	UPROPERTY(meta=(BindWidget, AutoAgentId="click_target", AutoAgentLogicalRole="button"))
	UImage* ClickTarget;

	UPROPERTY(meta=(BindWidget, AutoAgentId="click_target_variant_1", AutoAgentLogicalRole="button"))
	UImage* ClickTargetVariant1;

	UPROPERTY(meta=(BindWidget, AutoAgentId="click_target_variant_2", AutoAgentLogicalRole="button"))
	UImage* ClickTargetVariant2;

	UPROPERTY(meta=(BindWidget, AutoAgentId="click_target_variant_3", AutoAgentLogicalRole="button"))
	UImage* ClickTargetVariant3;

	UPROPERTY(meta=(BindWidget, AutoAgentId="click_target_variant_4", AutoAgentLogicalRole="button"))
	UImage* ClickTargetVariant4;

	UPROPERTY(meta=(BindWidget, AutoAgentId="click_target_variant_5", AutoAgentLogicalRole="button"))
	UImage* ClickTargetVariant5;

	UPROPERTY(meta=(BindWidget, AutoAgentId="text_target", AutoAgentLogicalRole="input"))
	UImage* TextTarget;

	UPROPERTY(meta=(BindWidget, AutoAgentId="text_target_text", AutoAgentLogicalRole="text_display"))
	UTextBlock* TextTargetText;

	UPROPERTY(meta=(BindWidget, AutoAgentId="drag_source", AutoAgentLogicalRole="drag_source"))
	UImage* DragSource;

	UPROPERTY(meta=(BindWidget, AutoAgentId="drag_target", AutoAgentLogicalRole="drop_target"))
	UImage* DragTarget;

	UPROPERTY(meta=(BindWidget, AutoAgentId="scroll_container", AutoAgentLogicalRole="scroll_container"))
	UImage* ScrollContainer;

	UPROPERTY(meta=(BindWidget, AutoAgentId="scroll_content", AutoAgentLogicalRole="image_only"))
	UCanvasPanel* ScrollContent;
};
