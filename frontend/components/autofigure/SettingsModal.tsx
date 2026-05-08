"use client"

import { useState, useEffect } from "react"
import {
    X,
    Settings2,
    Cpu,
    Lightbulb,
} from "lucide-react"
import { useAutoFigure } from "@/contexts/autofigure-context"
import { type ApiProtocol, type LLMProvider, LLM_PROVIDERS } from "@/lib/autofigure-types"

interface SettingsModalProps {
    isOpen: boolean
    onClose: () => void
}

type TabType = "general" | "llm"

export default function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
    const { config, updateConfig } = useAutoFigure()
    const [activeTab, setActiveTab] = useState<TabType>("general")

    // Close on Escape key
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                onClose()
            }
        }
        if (isOpen) {
            document.addEventListener("keydown", handleKeyDown)
            return () => document.removeEventListener("keydown", handleKeyDown)
        }
    }, [isOpen, onClose])

    // Prevent body scroll when modal is open
    useEffect(() => {
        if (isOpen) {
            document.body.style.overflow = "hidden"
        } else {
            document.body.style.overflow = ""
        }
        return () => {
            document.body.style.overflow = ""
        }
    }, [isOpen])

    if (!isOpen) return null

    const tabs = [
        { id: "general" as const, label: "General", icon: <Lightbulb className="w-4 h-4" /> },
        { id: "llm" as const, label: "LLM", icon: <Cpu className="w-4 h-4" /> },
    ]
    const protocolOptions: { value: ApiProtocol; label: string }[] = [
        { value: "openai-compatible", label: "OpenAI Compatible" },
        { value: "gemini-native", label: "Gemini Native" },
    ]

    return (
        <div className="af-modal-overlay" onClick={onClose}>
            <div
                className="af-modal"
                onClick={e => e.stopPropagation()}
            >
                {/* Header */}
                <div className="af-modal-header">
                    <div className="af-modal-title">
                        <div className="af-modal-icon">
                            <Settings2 className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <h2>Settings</h2>
                            <p>Configure generation parameters</p>
                        </div>
                    </div>
                    <button className="af-modal-close" onClick={onClose}>
                        <X className="w-5 h-5" />
                    </button>
                </div>

                {/* Tabs */}
                <div className="af-modal-tabs">
                    {tabs.map(tab => (
                        <button
                            key={tab.id}
                            className={`af-modal-tab ${activeTab === tab.id ? 'active' : ''}`}
                            onClick={() => setActiveTab(tab.id)}
                        >
                            {tab.icon}
                            {tab.label}
                        </button>
                    ))}
                </div>

                {/* Content */}
                <div className="af-modal-content">
                    {/* General Settings Tab */}
                    {activeTab === "general" && (
                        <div className="af-modal-section">
                            {/* Methodology Extraction - Only for paper content type */}
                            {config.contentType === 'paper' ? (
                                <div className="af-subsection">
                                    <h3 className="af-subsection-title">
                                        <Lightbulb className="w-4 h-4" />
                                        Methodology Extraction
                                    </h3>
                                    <p className="af-subsection-desc">
                                        Extract core methodology from paper to improve figure generation quality.
                                    </p>

                                    <label className="af-checkbox-group">
                                        <input
                                            type="checkbox"
                                            className="af-checkbox"
                                            checked={config.enableMethodologyExtraction}
                                            onChange={e => updateConfig({ enableMethodologyExtraction: e.target.checked })}
                                        />
                                        <span className="af-checkbox-label">Enable Methodology Extraction</span>
                                    </label>

                                    {config.enableMethodologyExtraction && (
                                        <div className="af-nested-form">
                                            <div className="af-form-row">
                                                <div className="af-form-group">
                                                    <label className="af-label">Provider</label>
                                                    <select
                                                        className="af-input"
                                                        value={config.methodologyLlmProvider || 'bianxie'}
                                                        onChange={e => {
                                                            const provider = e.target.value as LLMProvider
                                                            updateConfig({
                                                                methodologyLlmProvider: provider,
                                                                methodologyLlmProtocol: LLM_PROVIDERS[provider].defaultProtocol,
                                                                methodologyLlmBaseUrl: config.methodologyLlmBaseUrl || LLM_PROVIDERS[provider].defaultBaseUrl,
                                                            })
                                                        }}
                                                    >
                                                        {Object.entries(LLM_PROVIDERS).map(([key, value]) => (
                                                            <option key={key} value={key}>
                                                                {value.name}
                                                            </option>
                                                        ))}
                                                    </select>
                                                </div>

                                                <div className="af-form-group">
                                                    <label className="af-label">Model</label>
                                                    <input
                                                        type="text"
                                                        className="af-input"
                                                        value={config.methodologyLlmModel}
                                                        onChange={e => updateConfig({ methodologyLlmModel: e.target.value })}
                                                        placeholder={config.methodologyLlmProvider === 'openrouter'
                                                            ? 'e.g., google/gemini-3.1-pro-preview'
                                                            : config.methodologyLlmProvider === 'gemini'
                                                            ? 'e.g., gemini-3.1-pro-preview'
                                                            : 'e.g., gemini-3.1-pro-preview'}
                                                    />
                                                </div>
                                            </div>

                                            <div className="af-form-row">
                                                <div className="af-form-group">
                                                    <label className="af-label">Protocol</label>
                                                    <select
                                                        className="af-input"
                                                        value={config.methodologyLlmProtocol}
                                                        onChange={e => updateConfig({ methodologyLlmProtocol: e.target.value as ApiProtocol })}
                                                    >
                                                        {protocolOptions.map(option => (
                                                            <option key={option.value} value={option.value}>
                                                                {option.label}
                                                            </option>
                                                        ))}
                                                    </select>
                                                </div>

                                                <div className="af-form-group">
                                                    <label className="af-label">API Key</label>
                                                    <input
                                                        type="password"
                                                        className="af-input"
                                                        value={config.methodologyLlmApiKey}
                                                        onChange={e => updateConfig({ methodologyLlmApiKey: e.target.value })}
                                                        placeholder="Enter API key..."
                                                        autoComplete="new-password"
                                                        autoCorrect="off"
                                                        autoCapitalize="off"
                                                        spellCheck={false}
                                                        data-lpignore="true"
                                                        data-form-type="other"
                                                        data-1p-ignore="true"
                                                        name={`methodology-credential-${Date.now()}`}
                                                    />
                                                </div>
                                            </div>

                                            <div className="af-form-row">
                                                <div className="af-form-group">
                                                    <label className="af-label">Base URL (Optional)</label>
                                                    <input
                                                        type="text"
                                                        className="af-input"
                                                        value={config.methodologyLlmBaseUrl || ""}
                                                        onChange={e => updateConfig({ methodologyLlmBaseUrl: e.target.value })}
                                                        placeholder={config.methodologyLlmProvider === 'openrouter'
                                                            ? 'https://openrouter.ai/api/v1'
                                                            : config.methodologyLlmProvider === 'gemini'
                                                            ? 'https://generativelanguage.googleapis.com/v1beta'
                                                            : 'Custom API base URL...'}
                                                    />
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <p className="af-subsection-desc">
                                    No additional general settings available for this content type.
                                </p>
                            )}
                        </div>
                    )}

                    {/* LLM Configuration Tab */}
                    {activeTab === "llm" && (
                        <div className="af-modal-section">
                            <h3 className="af-subsection-title">
                                <Cpu className="w-4 h-4" />
                                Layout Generation LLM
                            </h3>
                            <p className="af-subsection-desc">
                                Configure the LLM used for generating figure layouts.
                            </p>

                            <div className="af-form-row">
                                <div className="af-form-group">
                                    <label className="af-label">Provider</label>
                                    <select
                                        className="af-input"
                                        value={config.llmProvider || 'bianxie'}
                                        onChange={e => {
                                            const provider = e.target.value as LLMProvider
                                            updateConfig({
                                                llmProvider: provider,
                                                llmProtocol: LLM_PROVIDERS[provider].defaultProtocol,
                                                baseUrl: config.baseUrl || LLM_PROVIDERS[provider].defaultBaseUrl,
                                            })
                                        }}
                                    >
                                        {Object.entries(LLM_PROVIDERS).map(([key, value]) => (
                                            <option key={key} value={key}>
                                                {value.name}
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                <div className="af-form-group">
                                    <label className="af-label">Model</label>
                                    <input
                                        type="text"
                                        className="af-input"
                                        value={config.model}
                                        onChange={e => updateConfig({ model: e.target.value })}
                                        placeholder={config.llmProvider === 'openrouter'
                                            ? 'e.g., google/gemini-3.1-pro-preview'
                                            : config.llmProvider === 'gemini'
                                            ? 'e.g., gemini-3.1-pro-preview'
                                            : 'e.g., gemini-3.1-pro-preview'}
                                    />
                                </div>
                            </div>

                            <div className="af-form-row">
                                <div className="af-form-group">
                                    <label className="af-label">Protocol</label>
                                    <select
                                        className="af-input"
                                        value={config.llmProtocol}
                                        onChange={e => updateConfig({ llmProtocol: e.target.value as ApiProtocol })}
                                    >
                                        {protocolOptions.map(option => (
                                            <option key={option.value} value={option.value}>
                                                {option.label}
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                <div className="af-form-group">
                                    <label className="af-label">API Key</label>
                                    <input
                                        type="password"
                                        className="af-input"
                                        value={config.apiKey}
                                        onChange={e => updateConfig({ apiKey: e.target.value })}
                                        placeholder="Enter API key..."
                                        autoComplete="new-password"
                                        autoCorrect="off"
                                        autoCapitalize="off"
                                        spellCheck={false}
                                        data-lpignore="true"
                                        data-form-type="other"
                                        data-1p-ignore="true"
                                        name={`layout-credential-${Date.now()}`}
                                    />
                                </div>
                            </div>

                            <div className="af-form-row">
                                <div className="af-form-group">
                                    <label className="af-label">Base URL (Optional)</label>
                                    <input
                                        type="text"
                                        className="af-input"
                                        value={config.baseUrl || ""}
                                        onChange={e => updateConfig({ baseUrl: e.target.value })}
                                        placeholder={config.llmProvider === 'openrouter'
                                            ? 'https://openrouter.ai/api/v1'
                                            : config.llmProvider === 'gemini'
                                            ? 'https://generativelanguage.googleapis.com/v1beta'
                                            : 'Custom API base URL...'}
                                    />
                                </div>
                            </div>
                        </div>
                    )}

                </div>

                {/* Footer */}
                <div className="af-modal-footer">
                    <button className="af-btn-secondary" onClick={onClose}>
                        Close
                    </button>
                </div>
            </div>
        </div>
    )
}
