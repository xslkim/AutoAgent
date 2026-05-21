// AutoAgent TASK-0205 — AutoAgentEditorModule.cpp
//
// Editor-only module: registers the AutoAgent Details Panel customization for
// all UWidget-derived classes and tears it down on shutdown / hot-reload.

#include "AutoAgentIdCustomization.h"
#include "Modules/ModuleManager.h"
#include "PropertyEditorModule.h"

class FAutoAgentEditorModule : public IModuleInterface
{
public:
	virtual void StartupModule() override
	{
		// Register the customization so the AutoAgent category appears in the
		// Details Panel whenever a UWidget (or any subclass) is selected.
		FPropertyEditorModule& PropertyModule =
			FModuleManager::LoadModuleChecked<FPropertyEditorModule>(
				TEXT("PropertyEditor"));

		PropertyModule.RegisterCustomClassLayout(
			TEXT("Widget"),
			FOnGetDetailCustomizationInstance::CreateStatic(
				&FAutoAgentIdCustomization::MakeInstance));

		PropertyModule.NotifyCustomizationModuleChanged();

		UE_LOG(LogTemp, Log, TEXT("[AutoAgent] Editor module loaded — "
								  "widget Details Panel customization registered."));
	}

	virtual void ShutdownModule() override
	{
		// Unregister on shutdown so hot-reload doesn't leave stale delegates.
		if (FModuleManager::Get().IsModuleLoaded(TEXT("PropertyEditor")))
		{
			FPropertyEditorModule& PropertyModule =
				FModuleManager::GetModuleChecked<FPropertyEditorModule>(
					TEXT("PropertyEditor"));
			PropertyModule.UnregisterCustomClassLayout(TEXT("Widget"));
		}
	}
};

IMPLEMENT_MODULE(FAutoAgentEditorModule, AutoAgentEditor)
