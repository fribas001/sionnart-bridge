/* Project compatibility adapter for Dr.Jit 1.5.0 + LLVM 22.1.8, Windows x64.
 * Preserve the Windows/MSVC target and calling convention; select ELF objects
 * for the legacy RuntimeDyld linker. All other LLVM exports are forwarded.
 * LLVMCreateMessage allocates with LLVM's allocator, as required by its API.
 */
__declspec(dllimport) char *LLVMCreateMessage(const char *);
char *bridge_GetDefaultTargetTriple(void) {
    return LLVMCreateMessage("x86_64-pc-windows-msvc-elf");
}
