using UnrealBuildTool;

public class AutoAgentEditor : ModuleRules
{
	public AutoAgentEditor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			// Runtime adapter — for FAutoAgentStableIdResolver
			"AutoAgent",
			// UMG widget base class
			"UMG",
			// Slate for Details Panel widgets
			"Slate",
			"SlateCore",
			"InputCore",
			// UE Details Panel customisation API
			"PropertyEditor",
			// Core editor utilities
			"UnrealEd",
		});
	}
}
