using UnrealBuildTool;
using System.Collections.Generic;

public class AutoAgentTestTarget : TargetRules
{
	public AutoAgentTestTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V5;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("AutoAgentTest");
	}
}
