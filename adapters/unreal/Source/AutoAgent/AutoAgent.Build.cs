using UnrealBuildTool;

public class AutoAgent : ModuleRules
{
	public AutoAgent(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		// -----------------------------------------------------------------------
		// AUTOAGENT_ENABLED
		// -----------------------------------------------------------------------
		// 1 in all configurations except Shipping.  Setting this to 0 strips the
		// WebSocket server, protocol handler, UMG reflector, and Slate input
		// driver from the packaged binary, keeping the Shipping-build size
		// increase well under 5 MB.
		//
		// Usage in source:
		//   #if AUTOAGENT_ENABLED
		//       ... runtime adapter code ...
		//   #endif
		// -----------------------------------------------------------------------
		bool bAutoAgentEnabled = Target.Configuration != UnrealTargetConfiguration.Shipping;
		PublicDefinitions.Add("AUTOAGENT_ENABLED=" + (bAutoAgentEnabled ? "1" : "0"));

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"UMG",
			"Slate",
			"SlateCore",
			"InputCore",
			"Sockets",
			"Networking",
			"Json",
			"ImageCore",
			"ImageWrapper",
		});
	}
}
