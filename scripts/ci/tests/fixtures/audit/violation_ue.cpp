// UE sample with several visual-write violations.
#include "LoginController.h"
#include "Components/Image.h"

void ULoginController::NativeConstruct()
{
    Super::NativeConstruct();

    LoginPanel->SetVisibility(ESlateVisibility::Hidden);      // violation: ue_visibility
    LoginPanel->SetRenderOpacity(0.5f);                       // violation: ue_render_opacity
    LoginPanel->SetColorAndOpacity(FLinearColor::Red);        // violation: ue_color_and_opacity
    LoginButton->SetBrushFromTexture(SomeTexture);            // violation: ue_brush_from_texture
    LoginPanel->SetRenderTransform(NewRT);                    // violation: ue_render_transform
}
