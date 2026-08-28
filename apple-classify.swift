import FoundationModels
import Foundation

// argv[1..] are the candidate folder names, in order. stdin is the prompt.
// Guided generation constrains the reply to one of those exact strings, so the
// ~3B on-device model cannot answer with prose, a number out of range, or a
// folder that does not exist — the failure modes that make small models
// unusable for routing when you ask them for free text.
let folders = Array(CommandLine.arguments.dropFirst())
guard !folders.isEmpty else { FileHandle.standardError.write("no folders\n".data(using:.utf8)!); exit(2) }

let prompt = String(data: FileHandle.standardInput.readDataToEndOfFile(), encoding: .utf8) ?? ""

guard case .available = SystemLanguageModel.default.availability else {
    FileHandle.standardError.write("apple-model unavailable\n".data(using: .utf8)!); exit(2)
}

let schema = DynamicGenerationSchema(
    name: "Routing",
    properties: [
        DynamicGenerationSchema.Property(
            name: "folder",
            schema: DynamicGenerationSchema(name: "Folder", anyOf: folders)
        )
    ]
)

let sem = DispatchSemaphore(value: 0)
var out = ""
var failure: String? = nil

Task {
    do {
        let sanitized = try GenerationSchema(root: schema, dependencies: [])
        let session = LanguageModelSession()
        let response = try await session.respond(
            to: prompt,
            schema: sanitized,
            options: GenerationOptions(temperature: 0.0)
        )
        if let value = try? response.content.value(String.self, forProperty: "folder") {
            out = value
        } else {
            out = response.content.debugDescription
        }
    } catch {
        failure = "\(error)"
    }
    sem.signal()
}
sem.wait()

if let failure { FileHandle.standardError.write("\(failure)\n".data(using:.utf8)!); exit(1) }
print(out)
