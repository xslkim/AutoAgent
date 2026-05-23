#include "AutoAgentOSInput.h"

#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include "Windows/WindowsHWrapper.h"
#include "Windows/HideWindowsPlatformTypes.h"
#endif

#if PLATFORM_MAC
#include <CoreGraphics/CoreGraphics.h>
#endif

#if PLATFORM_LINUX
#include <X11/Xlib.h>
#include <X11/extensions/XTest.h>
#include <dlfcn.h>
#endif

// ---------------------------------------------------------------------------
// Platform-specific implementation
// ---------------------------------------------------------------------------

#if PLATFORM_WINDOWS

static FVector2D GetVirtualScreenSize()
{
	int32 VW = GetSystemMetrics(78); // SM_CXVIRTUALSCREEN
	int32 VH = GetSystemMetrics(79); // SM_CYVIRTUALSCREEN
	return FVector2D(FMath::Max(VW, 1), FMath::Max(VH, 1));
}

static void SendOSMouse(int32 X, int32 Y, DWORD Flags, DWORD Data = 0)
{
	INPUT Inp = {};
	Inp.type = INPUT_MOUSE;
	Inp.mi.dx = X;
	Inp.mi.dy = Y;
	Inp.mi.dwFlags = Flags;
	Inp.mi.mouseData = Data;
	SendInput(1, &Inp, sizeof(INPUT));
}

static void SendOSKey(BYTE Vk, DWORD Flags)
{
	INPUT Inp = {};
	Inp.type = INPUT_KEYBOARD;
	Inp.ki.wVk = Vk;
	Inp.ki.dwFlags = Flags;
	SendInput(1, &Inp, sizeof(INPUT));
}

void FAutoAgentOSInput::Click(FVector2D ScreenPos, const FString& Button)
{
	FVector2D VSS = GetVirtualScreenSize();
	int32 AX = static_cast<int32>(ScreenPos.X * 65535.0 / VSS.X);
	int32 AY = static_cast<int32>(ScreenPos.Y * 65535.0 / VSS.Y);

	DWORD Down, Up;
	if (Button == TEXT("right"))
	{
		Down = MOUSEEVENTF_RIGHTDOWN;
		Up = MOUSEEVENTF_RIGHTUP;
	}
	else if (Button == TEXT("middle"))
	{
		Down = MOUSEEVENTF_MIDDLEDOWN;
		Up = MOUSEEVENTF_MIDDLEUP;
	}
	else
	{
		Down = MOUSEEVENTF_LEFTDOWN;
		Up = MOUSEEVENTF_LEFTUP;
	}

	SendOSMouse(AX, AY, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE);
	SendOSMouse(AX, AY, Down | MOUSEEVENTF_ABSOLUTE);
	SendOSMouse(AX, AY, Up | MOUSEEVENTF_ABSOLUTE);
}

void FAutoAgentOSInput::Drag(FVector2D From, FVector2D To, int32 DurationMs, int32 Steps)
{
	FVector2D VSS = GetVirtualScreenSize();
	auto Conv = [&](FVector2D P) -> TPair<int32, int32>
	{
		return {static_cast<int32>(P.X * 65535.0 / VSS.X),
				static_cast<int32>(P.Y * 65535.0 / VSS.Y)};
	};

	auto [X0, Y0] = Conv(From);
	auto [X1, Y1] = Conv(To);

	SendOSMouse(X0, Y0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE);
	SendOSMouse(X0, Y0, MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE);

	for (int32 I = 1; I <= Steps; ++I)
	{
		float T = static_cast<float>(I) / Steps;
		int32 CX = FMath::Lerp(X0, X1, T);
		int32 CY = FMath::Lerp(Y0, Y1, T);
		SendOSMouse(CX, CY, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE);
		FPlatformProcess::Sleep(0.001f);
	}

	SendOSMouse(X1, Y1, MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE);
}

void FAutoAgentOSInput::Scroll(FVector2D ScreenPos, float Delta)
{
	FVector2D VSS = GetVirtualScreenSize();
	int32 AX = static_cast<int32>(ScreenPos.X * 65535.0 / VSS.X);
	int32 AY = static_cast<int32>(ScreenPos.Y * 65535.0 / VSS.Y);
	int32 WD = static_cast<int32>(Delta * WHEEL_DELTA);

	SendOSMouse(AX, AY, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE);
	SendOSMouse(AX, AY, MOUSEEVENTF_WHEEL | MOUSEEVENTF_ABSOLUTE, WD);
}

void FAutoAgentOSInput::KeyPress(int32 VkCode)
{
	SendOSKey(static_cast<BYTE>(VkCode), 0);
	SendOSKey(static_cast<BYTE>(VkCode), KEYEVENTF_KEYUP);
}

void FAutoAgentOSInput::ShiftTab()
{
	SendOSKey(VK_SHIFT, 0);
	SendOSKey(VK_TAB, 0);
	SendOSKey(VK_TAB, KEYEVENTF_KEYUP);
	SendOSKey(VK_SHIFT, KEYEVENTF_KEYUP);
}

int32 FAutoAgentOSInput::MapKey(const FString& Key)
{
	FString K = Key.ToLower().TrimStartAndEnd();
	if (K == TEXT("enter") || K == TEXT("return") || K == TEXT("submit"))
		return VK_RETURN;
	else if (K == TEXT("escape") || K == TEXT("esc") || K == TEXT("cancel"))
		return VK_ESCAPE;
	else if (K == TEXT("tab"))
		return VK_TAB;
	else
		return -1;
}

#elif PLATFORM_MAC

static void PostAndRelease(CGEventRef Evt)
{
	if (Evt)
	{
		CGEventPost(kCGHIDEventTap, Evt);
		CFRelease(Evt);
	}
}

static CGPoint ToCGPoint(FVector2D P)
{
	CGRect Bounds = CGDisplayBounds(CGMainDisplayID());
	return CGPoint{P.X, Bounds.size.height - P.Y};
}

void FAutoAgentOSInput::Click(FVector2D ScreenPos, const FString& Button)
{
	CGPoint Pt = ToCGPoint(ScreenPos);

	CGEventType Down, Up;
	CGMouseButton MBtn;
	if (Button == TEXT("right"))
	{
		Down = kCGEventRightMouseDown;
		Up = kCGEventRightMouseUp;
		MBtn = kCGMouseButtonRight;
	}
	else if (Button == TEXT("middle"))
	{
		Down = kCGEventOtherMouseDown;
		Up = kCGEventOtherMouseUp;
		MBtn = kCGMouseButtonCenter;
	}
	else
	{
		Down = kCGEventLeftMouseDown;
		Up = kCGEventLeftMouseUp;
		MBtn = kCGMouseButtonLeft;
	}

	PostAndRelease(CGEventCreateMouseEvent(nullptr, kCGEventMouseMoved, Pt, kCGMouseButtonLeft));
	PostAndRelease(CGEventCreateMouseEvent(nullptr, Down, Pt, MBtn));
	PostAndRelease(CGEventCreateMouseEvent(nullptr, Up, Pt, MBtn));
}

void FAutoAgentOSInput::Drag(FVector2D From, FVector2D To, int32 DurationMs, int32 Steps)
{
	CGPoint F = ToCGPoint(From);
	CGPoint T = ToCGPoint(To);

	PostAndRelease(CGEventCreateMouseEvent(nullptr, kCGEventMouseMoved, F, kCGMouseButtonLeft));
	PostAndRelease(CGEventCreateMouseEvent(nullptr, kCGEventLeftMouseDown, F, kCGMouseButtonLeft));

	for (int32 I = 1; I <= Steps; ++I)
	{
		float Tf = static_cast<float>(I) / Steps;
		CGPoint C{F.x + (T.x - F.x) * Tf, F.y + (T.y - F.y) * Tf};
		PostAndRelease(CGEventCreateMouseEvent(nullptr, kCGEventLeftMouseDragged, C, kCGMouseButtonLeft));
		FPlatformProcess::Sleep(0.001f);
	}

	PostAndRelease(CGEventCreateMouseEvent(nullptr, kCGEventLeftMouseUp, T, kCGMouseButtonLeft));
}

void FAutoAgentOSInput::Scroll(FVector2D ScreenPos, float Delta)
{
	CGPoint Pt = ToCGPoint(ScreenPos);
	PostAndRelease(CGEventCreateMouseEvent(nullptr, kCGEventMouseMoved, Pt, kCGMouseButtonLeft));
	PostAndRelease(CGEventCreateScrollWheelEvent(nullptr, kCGScrollEventUnitPixel, 1, static_cast<int32>(Delta * 3)));
}

void FAutoAgentOSInput::KeyPress(int32 CgKeyCode)
{
	PostAndRelease(CGEventCreateKeyboardEvent(nullptr, static_cast<CGKeyCode>(CgKeyCode), true));
	PostAndRelease(CGEventCreateKeyboardEvent(nullptr, static_cast<CGKeyCode>(CgKeyCode), false));
}

void FAutoAgentOSInput::ShiftTab()
{
	PostAndRelease(CGEventCreateKeyboardEvent(nullptr, static_cast<CGKeyCode>(CGKEY_LSHIFT), true));
	PostAndRelease(CGEventCreateKeyboardEvent(nullptr, static_cast<CGKeyCode>(CGKEY_TAB), true));
	PostAndRelease(CGEventCreateKeyboardEvent(nullptr, static_cast<CGKeyCode>(CGKEY_TAB), false));
	PostAndRelease(CGEventCreateKeyboardEvent(nullptr, static_cast<CGKeyCode>(CGKEY_LSHIFT), false));
}

int32 FAutoAgentOSInput::MapKey(const FString& Key)
{
	FString K = Key.ToLower().TrimStartAndEnd();
	if (K == TEXT("enter") || K == TEXT("return") || K == TEXT("submit"))
		return CGKEY_RETURN;
	else if (K == TEXT("escape") || K == TEXT("esc") || K == TEXT("cancel"))
		return CGKEY_ESCAPE;
	else if (K == TEXT("tab"))
		return CGKEY_TAB;
	else
		return -1;
}

#elif PLATFORM_LINUX

// Lazy-loaded X11 / XTest function pointers (avoid link-time deps).
static void* GX11Lib = nullptr;
static Display* GX11Display = nullptr;
static int GX11Screen = 0;
static int (*GXOpenDisplay)(const char*) = nullptr;
static int (*GXDefaultScreen)(Display*) = nullptr;
static int (*GXFlush)(Display*) = nullptr;
static int (*GXDisplayWidth)(Display*, int) = nullptr;
static int (*GXDisplayHeight)(Display*, int) = nullptr;
static int (*GXTestFakeMotionEvent)(Display*, int, int, int, unsigned long) = nullptr;
static int (*GXTestFakeButtonEvent)(Display*, int, unsigned int, Bool, unsigned long) = nullptr;
static int (*GXTestFakeKeyEvent)(Display*, unsigned int, Bool, unsigned long) = nullptr;

static void InitX11()
{
	if (GX11Display)
		return;
	GX11Lib = dlopen("libX11.so.6", RTLD_NOW);
	void* Xtst = dlopen("libXtst.so.6", RTLD_NOW);
	if (!GX11Lib || !Xtst)
		return;

	*(void**)&GXOpenDisplay = dlsym(GX11Lib, "XOpenDisplay");
	*(void**)&GXDefaultScreen = dlsym(GX11Lib, "XDefaultScreen");
	*(void**)&GXFlush = dlsym(GX11Lib, "XFlush");
	*(void**)&GXDisplayWidth = dlsym(GX11Lib, "XDisplayWidth");
	*(void**)&GXDisplayHeight = dlsym(GX11Lib, "XDisplayHeight");

	*(void**)&GXTestFakeMotionEvent = dlsym(Xtst, "XTestFakeMotionEvent");
	*(void**)&GXTestFakeButtonEvent = dlsym(Xtst, "XTestFakeButtonEvent");
	*(void**)&GXTestFakeKeyEvent = dlsym(Xtst, "XTestFakeKeyEvent");

	if (GXOpenDisplay)
		GX11Display = (Display*)GXOpenDisplay(nullptr);
	if (GX11Display)
		GX11Screen = GXDefaultScreen ? GXDefaultScreen(GX11Display) : 0;
}

static int GetX11Width() { return GXDisplayWidth ? GXDisplayWidth(GX11Display, GX11Screen) : 1920; }
static int GetX11Height() { return GXDisplayHeight ? GXDisplayHeight(GX11Display, GX11Screen) : 1080; }

void FAutoAgentOSInput::Click(FVector2D ScreenPos, const FString& Button)
{
	InitX11();
	if (!GX11Display)
		return;
	int X = FMath::Clamp(static_cast<int32>(ScreenPos.X), 0, GetX11Width() - 1);
	int Y = FMath::Clamp(static_cast<int32>(ScreenPos.Y), 0, GetX11Height() - 1);

	unsigned int Btn;
	if (Button == TEXT("right"))
		Btn = 3;
	else if (Button == TEXT("middle"))
		Btn = 2;
	else
		Btn = 1;

	GXTestFakeMotionEvent(GX11Display, GX11Screen, X, Y, 0);
	GXTestFakeButtonEvent(GX11Display, Btn, True, 0);
	GXTestFakeButtonEvent(GX11Display, Btn, False, 0);
	GXFlush(GX11Display);
}

void FAutoAgentOSInput::Drag(FVector2D From, FVector2D To, int32 DurationMs, int32 Steps)
{
	InitX11();
	if (!GX11Display)
		return;
	int W = GetX11Width(), H = GetX11Height();
	int X0 = FMath::Clamp(static_cast<int32>(From.X), 0, W - 1);
	int Y0 = FMath::Clamp(static_cast<int32>(From.Y), 0, H - 1);
	int X1 = FMath::Clamp(static_cast<int32>(To.X), 0, W - 1);
	int Y1 = FMath::Clamp(static_cast<int32>(To.Y), 0, H - 1);

	GXTestFakeMotionEvent(GX11Display, GX11Screen, X0, Y0, 0);
	GXTestFakeButtonEvent(GX11Display, 1, True, 0);
	GXFlush(GX11Display);

	for (int32 I = 1; I <= Steps; ++I)
	{
		float T = static_cast<float>(I) / Steps;
		int CX = FMath::Lerp(X0, X1, T);
		int CY = FMath::Lerp(Y0, Y1, T);
		GXTestFakeMotionEvent(GX11Display, GX11Screen, CX, CY, 0);
		GXFlush(GX11Display);
		FPlatformProcess::Sleep(0.001f);
	}

	GXTestFakeButtonEvent(GX11Display, 1, False, 0);
	GXFlush(GX11Display);
}

void FAutoAgentOSInput::Scroll(FVector2D ScreenPos, float Delta)
{
	InitX11();
	if (!GX11Display)
		return;
	int X = FMath::Clamp(static_cast<int32>(ScreenPos.X), 0, GetX11Width() - 1);
	int Y = FMath::Clamp(static_cast<int32>(ScreenPos.Y), 0, GetX11Height() - 1);

	GXTestFakeMotionEvent(GX11Display, GX11Screen, X, Y, 0);
	int Clicks = FMath::Max(1, FMath::Abs(static_cast<int32>(Delta * 3)));
	unsigned int Btn = Delta > 0 ? 4u : 5u;
	for (int I = 0; I < Clicks; ++I)
	{
		GXTestFakeButtonEvent(GX11Display, Btn, True, 0);
		GXTestFakeButtonEvent(GX11Display, Btn, False, 0);
	}
	GXFlush(GX11Display);
}

void FAutoAgentOSInput::KeyPress(int32 XKeyCode)
{
	InitX11();
	if (!GX11Display)
		return;
	GXTestFakeKeyEvent(GX11Display, static_cast<unsigned int>(XKeyCode), True, 0);
	GXTestFakeKeyEvent(GX11Display, static_cast<unsigned int>(XKeyCode), False, 0);
	GXFlush(GX11Display);
}

void FAutoAgentOSInput::ShiftTab()
{
	InitX11();
	if (!GX11Display)
		return;
	GXTestFakeKeyEvent(GX11Display, XK_LSHIFT, True, 0);
	GXTestFakeKeyEvent(GX11Display, XK_TAB, True, 0);
	GXTestFakeKeyEvent(GX11Display, XK_TAB, False, 0);
	GXTestFakeKeyEvent(GX11Display, XK_LSHIFT, False, 0);
	GXFlush(GX11Display);
}

int32 FAutoAgentOSInput::MapKey(const FString& Key)
{
	FString K = Key.ToLower().TrimStartAndEnd();
	if (K == TEXT("enter") || K == TEXT("return") || K == TEXT("submit"))
		return XK_RETURN;
	else if (K == TEXT("escape") || K == TEXT("esc") || K == TEXT("cancel"))
		return XK_ESCAPE;
	else if (K == TEXT("tab"))
		return XK_TAB;
	else
		return -1;
}

#else

// Stubs for unsupported platforms.
void FAutoAgentOSInput::Click(FVector2D, const FString&) {}
void FAutoAgentOSInput::Drag(FVector2D, FVector2D, int32, int32) {}
void FAutoAgentOSInput::Scroll(FVector2D, float) {}
void FAutoAgentOSInput::KeyPress(int32) {}
void FAutoAgentOSInput::ShiftTab() {}
int32 FAutoAgentOSInput::MapKey(const FString&) { return -1; }

#endif
