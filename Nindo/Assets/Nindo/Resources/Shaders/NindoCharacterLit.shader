// Personajes (Kaito, enemigos, jefes, NPC). Basado en Simple Lit de URP 17 (Blinn-Phong, luz principal +
// adicionales con Forward+, sombras, niebla, SH) con dos agregados para que se lean de noche desde la
// cámara alta, donde un personaje mide ~100 px:
//  - rim de vista frío (#9fc2ff, potencia 3): separa la silueta del suelo oscuro sin aclarar el color
//    (un traje negro sigue siendo negro adentro, el borde marca la forma) — audit_models MODEL-03
//  - _EmissionColor siempre activo (sin keyword): el filo 'Glint' de las armas (CharacterGlint, el aviso del
//    golpe), los ojos de Gorō, los brillos de los ojos de Kaito y el destello de la bandana
// El brillo especular sale de _Smoothness (tela/piel ~0.15 casi mate; acero ~0.6 con un reflejo chico).
// CharacterFactory convierte los materiales del FBX a este shader copiando _BaseColor/_BaseMap/_EmissionColor.
Shader "Nindo/CharacterLit"
{
    Properties
    {
        [MainTexture] _BaseMap ("Base Map", 2D) = "white" {}
        [MainColor] _BaseColor ("Base Color", Color) = (1, 1, 1, 1)
        _Smoothness ("Smoothness", Range(0, 1)) = 0.15
        [HDR] _EmissionColor ("Emission", Color) = (0, 0, 0, 1)
        _RimColor ("Rim", Color) = (0.624, 0.761, 1, 1)
        _RimStrength ("Rim Strength", Range(0, 1)) = 0.3
        _RimPower ("Rim Power", Range(0.5, 8)) = 3
        _Cutoff ("Alpha Cutoff", Range(0, 1)) = 0.5
        [HideInInspector] _Surface ("__surface", Float) = 0
        [HideInInspector] _Cull ("__cull", Float) = 2
    }

    SubShader
    {
        Tags { "RenderType" = "Opaque" "RenderPipeline" = "UniversalPipeline" "UniversalMaterialType" = "SimpleLit" "IgnoreProjector" = "True" }
        LOD 300

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/SurfaceInput.hlsl"

        // mismas propiedades en todas las pasadas: compatible con el SRP Batcher
        CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseColor;
            half4 _EmissionColor;
            half4 _RimColor;
            half _Smoothness;
            half _RimStrength;
            half _RimPower;
            half _Cutoff;
            half _Surface;
        CBUFFER_END
        ENDHLSL

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }
            Cull [_Cull]
            ZWrite On

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex Vert
            #pragma fragment Frag

            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ EVALUATE_SH_MIXED EVALUATE_SH_VERTEX
            #pragma multi_compile _ LIGHTMAP_SHADOW_MIXING
            #pragma multi_compile _ SHADOWS_SHADOWMASK
            #pragma multi_compile _ _LIGHT_LAYERS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _SCREEN_SPACE_OCCLUSION
            #pragma multi_compile_fragment _ _LIGHT_COOKIES
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/ProbeVolumeVariants.hlsl"
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"
            #pragma multi_compile_instancing

            // Blinn-Phong con color especular propio (UniversalFragmentBlinnPhong lo usa solo con esta define)
            #define _SPECULAR_COLOR 1
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 positionWS : TEXCOORD1;
                half3 normalWS : TEXCOORD2;
                half fogFactor : TEXCOORD3;
                DECLARE_LIGHTMAP_OR_SH(staticLightmapUV, vertexSH, 4);
            #ifdef _ADDITIONAL_LIGHTS_VERTEX
                half3 vertexLight : TEXCOORD5;
            #endif
            #ifdef USE_APV_PROBE_OCCLUSION
                float4 probeOcclusion : TEXCOORD6;
            #endif
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings Vert(Attributes input)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                VertexPositionInputs p = GetVertexPositionInputs(input.positionOS.xyz);
                VertexNormalInputs n = GetVertexNormalInputs(input.normalOS);
                o.positionCS = p.positionCS;
                o.positionWS = p.positionWS;
                o.normalWS = NormalizeNormalPerVertex(n.normalWS);
                o.uv = TRANSFORM_TEX(input.uv, _BaseMap);
                o.fogFactor = ComputeFogFactor(p.positionCS.z);
                OUTPUT_SH4(p.positionWS, o.normalWS.xyz, GetWorldSpaceNormalizeViewDir(p.positionWS), o.vertexSH, o.probeOcclusion);
            #ifdef _ADDITIONAL_LIGHTS_VERTEX
                o.vertexLight = VertexLighting(p.positionWS, n.normalWS);
            #endif
                return o;
            }

            half4 Frag(Varyings input) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                half4 albedo = SampleAlbedoAlpha(input.uv, TEXTURE2D_ARGS(_BaseMap, sampler_BaseMap)) * _BaseColor;

                SurfaceData s = (SurfaceData)0;
                s.albedo = albedo.rgb;
                s.alpha = 1;
                s.smoothness = _Smoothness;
                // reflejo solo en lo liso: con 0.15 (tela) casi nada, con 0.6 (acero) un punto de luz
                s.specular = (half3)(_Smoothness * _Smoothness * 0.8);
                s.occlusion = 1;
                s.emission = _EmissionColor.rgb;
                s.normalTS = half3(0, 0, 1);

                InputData d = (InputData)0;
                d.positionWS = input.positionWS;
                d.positionCS = input.positionCS;
                d.normalWS = NormalizeNormalPerPixel(input.normalWS);
                d.viewDirectionWS = GetWorldSpaceNormalizeViewDir(input.positionWS);
            #if defined(MAIN_LIGHT_CALCULATE_SHADOWS)
                d.shadowCoord = TransformWorldToShadowCoord(input.positionWS);
            #endif
                d.fogCoord = InitializeInputDataFog(float4(input.positionWS, 1.0), input.fogFactor);
            #ifdef _ADDITIONAL_LIGHTS_VERTEX
                d.vertexLighting = input.vertexLight;
            #endif
                d.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);
            #if !defined(LIGHTMAP_ON) && (defined(PROBE_VOLUMES_L1) || defined(PROBE_VOLUMES_L2))
                d.bakedGI = SAMPLE_GI(input.vertexSH, GetAbsolutePositionWS(d.positionWS), d.normalWS, d.viewDirectionWS,
                                      input.positionCS.xy, input.probeOcclusion, d.shadowMask);
            #else
                d.bakedGI = SAMPLE_GI(input.staticLightmapUV, input.vertexSH, d.normalWS);
                d.shadowMask = SAMPLE_SHADOWMASK(input.staticLightmapUV);
            #endif

                half4 color = UniversalFragmentBlinnPhong(d, s);

                // rim de vista: más fuerte en los bordes de la silueta (normal casi perpendicular a la cámara)
                half ndv = saturate(dot(d.normalWS, d.viewDirectionWS));
                color.rgb += _RimColor.rgb * (pow(1.0h - ndv, _RimPower) * _RimStrength);

                color.rgb = MixFog(color.rgb, d.fogCoord);
                color.a = 1;
                return color;
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On
            ZTest LEqual
            ColorMask 0
            Cull [_Cull]

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex ShadowPassVertex
            #pragma fragment ShadowPassFragment
            #pragma multi_compile_instancing
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #include "Packages/com.unity.render-pipelines.universal/Shaders/ShadowCasterPass.hlsl"
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On
            ColorMask R
            Cull [_Cull]

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex DepthOnlyVertex
            #pragma fragment DepthOnlyFragment
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/Shaders/DepthOnlyPass.hlsl"
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode" = "DepthNormals" }
            ZWrite On
            Cull [_Cull]

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex DepthNormalsVertex
            #pragma fragment DepthNormalsFragment
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/DepthNormalsPass.hlsl"
            ENDHLSL
        }
    }

    Fallback "Universal Render Pipeline/Simple Lit"
}
