// AutoFigure TypeScript Types

export type ContentType = 'paper' | 'survey' | 'blog' | 'textbook'
// Supported LLM providers
export type LLMProvider = 'custom' | 'bianxie' | 'openrouter' | 'gemini'
export type ApiProtocol = 'openai-compatible' | 'gemini-native'
export type EnhancementMode = 'none' | 'code2prompt'
export type SessionStatus = 'idle' | 'generating' | 'waiting_feedback' | 'enhancing' | 'completed' | 'error'

export interface AutoFigureConfig {
    // Content Configuration
    contentType: ContentType
    inputText: string

    // Iteration Parameters
    maxIterations: number
    qualityThreshold: number
    minImprovement: number
    humanInLoop: boolean

    // LLM Configuration (for layout generation)
    llmProvider: LLMProvider
    llmProtocol: ApiProtocol
    apiKey: string
    baseUrl?: string
    model: string

    // Output Configuration
    svgWidth: number
    svgHeight: number

    // Methodology Extraction Configuration (for paper content type)
    enableMethodologyExtraction: boolean
    methodologyLlmProvider: LLMProvider
    methodologyLlmProtocol: ApiProtocol
    methodologyLlmApiKey: string
    methodologyLlmBaseUrl?: string
    methodologyLlmModel: string

    // Beautification (shown after layout finalization)
    enhancementMode: EnhancementMode
    artStyle: string
    enhancementCount: number

    // Enhancement LLM Configuration (user-provided, for code2prompt conversion)
    enhancementLlmProvider: LLMProvider
    enhancementLlmProtocol: ApiProtocol
    enhancementLlmApiKey: string
    enhancementLlmBaseUrl?: string
    enhancementLlmModel: string

    // Image Generation API Configuration (user-provided)
    imageGenProvider: LLMProvider
    imageGenProtocol: ApiProtocol
    imageGenApiKey: string
    imageGenBaseUrl?: string
    imageGenModel: string
}

export interface EvaluationScores {
    aesthetic_design: number
    content_fidelity: number
    placeholder_usage: number
}

export interface EvaluationResult {
    scores: EvaluationScores
    overall_quality: number
    critique_summary: string
    specific_issues: string[]
    improvement_suggestions: string[]
}

export interface IterationResult {
    iteration: number
    xml: string
    pngBase64?: string
    evaluation?: EvaluationResult
    humanFeedback?: string
    humanScore?: number
    timestamp: string
}

export interface AutoFigureSession {
    sessionId: string
    status: SessionStatus
    config: AutoFigureConfig
    currentIteration: number
    iterations: IterationResult[]
    finalXml?: string
    finalPngBase64?: string  // PNG preview of user-edited final XML
    enhancedImages?: EnhancedImage[]
    error?: string
}

export interface EnhancedImage {
    variant: number
    pngBase64: string | null
    status: 'pending' | 'processing' | 'completed' | 'failed'
    error?: string
}

export interface StartGenerationResponse {
    sessionId: string
    iteration: number
    xml: string
    pngBase64: string
    status: SessionStatus
}

export interface ContinueIterationRequest {
    currentXml: string
    humanFeedback?: string
    humanScore?: number
}

export interface ContinueIterationResponse {
    iteration: number
    xml: string
    pngBase64: string
    evaluation: EvaluationResult
    status: SessionStatus
}

export interface EnhanceRequest {
    mode: EnhancementMode
    artStyle: string
    variantCount: number
    // User-provided LLM config for code2prompt
    enhancementLlmProvider: LLMProvider
    enhancementLlmProtocol: ApiProtocol
    enhancementLlmApiKey: string
    enhancementLlmBaseUrl?: string
    enhancementLlmModel: string
    // User-provided image generation config
    imageGenProvider: LLMProvider
    imageGenProtocol: ApiProtocol
    imageGenApiKey: string
    imageGenBaseUrl?: string
    imageGenModel: string
}

export interface EnhanceStatusResponse {
    status: 'processing' | 'completed' | 'failed'
    progress: number
    completedVariants: number
    totalVariants: number
    images: EnhancedImage[]
}

// Default configuration values - all API credentials must be provided by user
export const DEFAULT_CONFIG: AutoFigureConfig = {
    contentType: 'paper',
    inputText: '',
    maxIterations: 5,
    qualityThreshold: 9.0,
    minImprovement: 0.2,
    humanInLoop: true,
    llmProvider: 'bianxie',
    llmProtocol: 'openai-compatible',
    apiKey: '',
    baseUrl: '',  // User must provide
    model: '',    // User must provide
    svgWidth: 1333,
    svgHeight: 750,
    // Methodology extraction config (for paper content type)
    enableMethodologyExtraction: true,
    methodologyLlmProvider: 'bianxie',
    methodologyLlmProtocol: 'openai-compatible',
    methodologyLlmApiKey: '',
    methodologyLlmBaseUrl: '',  // User must provide
    methodologyLlmModel: '',    // User must provide
    // Beautification config
    enhancementMode: 'code2prompt',
    artStyle: '',  // User must provide their own custom art style description
    enhancementCount: 3,
    // Enhancement LLM config (user must provide)
    enhancementLlmProvider: 'bianxie',
    enhancementLlmProtocol: 'openai-compatible',
    enhancementLlmApiKey: '',
    enhancementLlmBaseUrl: '',  // User must provide
    enhancementLlmModel: '',    // User must provide
    // Image generation config (user must provide)
    imageGenProvider: 'bianxie',
    imageGenProtocol: 'openai-compatible',
    imageGenApiKey: '',
    imageGenBaseUrl: '',  // User must provide
    imageGenModel: '',    // User must provide
}

// LLM Provider configurations
export const LLM_PROVIDERS: Record<LLMProvider, { name: string; defaultBaseUrl: string; defaultProtocol: ApiProtocol; description: string }> = {
    custom: {
        name: 'Custom',
        defaultBaseUrl: '',
        defaultProtocol: 'openai-compatible',
        description: 'Custom endpoint - choose protocol and enter base URL',
    },
    bianxie: {
        name: 'BianXie',
        defaultBaseUrl: 'https://api.bianxie.ai/v1',
        defaultProtocol: 'openai-compatible',
        description: 'BianXie AI API (OpenAI-compatible)',
    },
    openrouter: {
        name: 'OpenRouter',
        defaultBaseUrl: 'https://openrouter.ai/api/v1',
        defaultProtocol: 'openai-compatible',
        description: 'OpenRouter API - Access multiple AI models',
    },
    gemini: {
        name: 'Google Gemini',
        defaultBaseUrl: 'https://generativelanguage.googleapis.com/v1beta',
        defaultProtocol: 'gemini-native',
        description: 'Google Gemini API - Direct access to Gemini models',
    },
}
