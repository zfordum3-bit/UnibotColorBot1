#pragma once // Prevent header file from being included multiple times

#include <windows.h>
#include <cstdint> // Include this header to use uint32_t

// Declare the enums we will use
// Note: According to your new code, I have placed the enums under the Send namespace
namespace Send {
    enum class Error {
        Success = 0, InvalidArgument = 1, DeviceNotFound = 2, DriverError = 3
    };
    enum class SendType {
        SendInput = 0, Logitech = 1, Razer = 2, DD = 3,
        MouClassInputInjection = 4, LogitechGHubNew = 5, AnyDriver = 100
    };
    enum class MoveMode {
        Absolute = 0, Relative = 1
    };
    enum class InitFlags {
        // ... Define any flags you need here, or leave empty if not used
    };
}


// Use class to encapsulate all DLL-related state and behavior
class InputSimulator {
public:
    InputSimulator();
    ~InputSimulator();

    Send::Error Init(Send::SendType type);
    // MoveRelative
    void MoveRelative(int dx, int dy);
    // MoveAbsolute cannot be implemented for now because we don't know how the new function handles absolute movement, so comment it out
    // void MoveAbsolute(int x, int y);

private:
    HMODULE hDll;

    // --- Use new, correct function pointer types ---
    typedef Send::Error(__stdcall* PFN_IbSendInit)(Send::SendType type, Send::InitFlags flags, void* argument);
    typedef void(__stdcall* PFN_IbSendDestroy)();
    // This is key: Define new mouse move function pointer
    typedef bool(__stdcall* PFN_IbSendMouseMove)(uint32_t dx, uint32_t dy, Send::MoveMode mode);

    // --- Update function pointer variables ---
    PFN_IbSendInit pIbSendInit;
    PFN_IbSendDestroy pIbSendDestroy;
    // Use new mouse move pointer
    PFN_IbSendMouseMove pIbSendMouseMove;

    bool is_initialized_successfully;
};