// Disolución con trama (dither) de lo que tapa la vista: árboles, bambú, casas, muros. CameraOcclusion pone este
// material SOLO mientras un objeto estorba y devuelve el original al terminar (los personajes no se tocan).
// Se ve igual que el mundo (paleta + luna con sombras + faroles + ambiente + niebla, sin especular como el Lit de la
// paleta; con viento si viene del follaje) y descarta píxeles con una trama de Bayer 4x4:
//   _NindoFade      0..1 todo el objeto (lo que está pegado a la cámara)
//   _NindoHoleFade  0..1 solo dentro de los "huecos": conos desde la cámara hacia Kaito, el fijado, el jefe y quien
//                   está por pegar (_NindoHoles, globales: xyz = punto del personaje, w = tangente del radio angular).
//                   El hueco se calcula en mundo (no en pantalla): no depende de si el render target está invertido.
// Una trama y no transparencia: no hay que ordenar mallas enormes ni se pierde la escritura de profundidad.
// El viento es multi_compile (no shader_feature): los materiales se crean en runtime y el build tiene que traer la variante.
Shader "Nindo/Occluder Fade"
{
    Properties
    {
        [MainTexture] _BaseMap ("Paleta", 2D) = "white" {}
        [MainColor] _BaseColor ("Color", Color) = (1, 1, 1, 1)
        _EmissionMap ("Emisión", 2D) = "white" {}
        [HDR] _EmissionColor ("Color de emisión", Color) = (0, 0, 0, 1)
        _WindStrength ("Fuerza del viento", Range(0, 1)) = 0.14
        _WindSpeed ("Velocidad", Range(0, 5)) = 1.4
        _WindScale ("Escala de las ráfagas", Range(0.01, 1)) = 0.08
        _Flutter ("Aleteo", Range(0, 0.2)) = 0.03
        _Wrap ("Luz que atraviesa (wrap)", Range(0, 1)) = 0
        [Enum(UnityEngine.Rendering.CullMode)] _Cull ("Cull", Float) = 2
        _NindoFade ("Disolución entera", Range(0, 1)) = 0
        _NindoHoleFade ("Disolución en los huecos", Range(0, 1)) = 0
        _NindoShadowFade ("Cuánto de la disolución pasa a la sombra", Range(0, 1)) = 0.6
        _DiffuseScale ("Difuso del material original", Range(0, 1)) = 1
        [Toggle(_NINDO_WIND)] _NindoWind ("Viento (follaje)", Float) = 0
    }

    SubShader
    {
        Tags { "RenderType" = "Opaque" "RenderPipeline" = "UniversalPipeline" "Queue" = "AlphaTest" }
        LOD 200
        Cull [_Cull]

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseColor;
            half4 _EmissionColor;
            float _WindStrength;
            float _WindSpeed;
            float _WindScale;
            float _Flutter;
            half _Wrap;
            half _NindoFade;
            half _NindoHoleFade;
            half _NindoShadowFade;
            half _DiffuseScale;
        CBUFFER_END

        TEXTURE2D(_BaseMap);
        SAMPLER(sampler_BaseMap);
        TEXTURE2D(_EmissionMap);

        float4 _NindoHoles[4];

        // ---- mismo viento que Nindo/Foliage Wind (si no, la hoja "salta" al cambiar de material)
        float WindWeight(float r)
        {
            r = saturate(r);
            return saturate(r <= 0.0031308 ? r * 12.92 : 1.055 * pow(r, 1.0 / 2.4) - 0.055);
        }

        float3 WindOffset(float3 positionWS, float weight)
        {
            float t = _Time.y * _WindSpeed;
            float phase = dot(positionWS.xz, float2(_WindScale, _WindScale * 0.73));
            float gust = sin(t + phase) * 0.6 + sin(t * 0.37 + phase * 0.5) * 0.4;
            float flutter = sin(t * 7.3 + positionWS.y * 3.1 + phase * 9.0) * _Flutter;
            float3 dir = normalize(float3(1.0, 0.0, 0.45));
            return (dir * (gust * _WindStrength + flutter) + float3(0, -abs(gust) * _WindStrength * 0.15, 0)) * weight;
        }

        float3 Displace(float3 positionWS, float4 color)
        {
            #if defined(_NINDO_WIND)
            positionWS += WindOffset(positionWS, WindWeight(color.r));
            #endif
            return positionWS;
        }

        // umbral de Bayer 4x4 en (0, 1): con fade f se descarta la fracción f de los píxeles, repartida parejo
        static const float NindoBayer[16] = { 0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5 };
        float Bayer4(float2 pixel)
        {
            uint2 p = uint2(pixel) & 3u;
            return (NindoBayer[p.y * 4 + p.x] + 0.5) / 16.0;
        }

        // 1 dentro de algún cono cámara -> personaje (y por delante de él), borde suave
        float HoleMask(float3 positionWS)
        {
            float mask = 0;
            float3 v = positionWS - _WorldSpaceCameraPos;
            [unroll] for (int i = 0; i < 4; i++)
            {
                float4 h = _NindoHoles[i];
                if (h.w <= 0) continue;
                float3 a = h.xyz - _WorldSpaceCameraPos;
                float la = length(a);
                float3 ad = a / max(la, 1e-3);
                float t = dot(v, ad);
                float tanAng = length(v - ad * t) / max(t, 0.05);
                float inside = 1.0 - smoothstep(h.w * 0.7, h.w, tanAng);
                // solo lo que está entre la cámara y el personaje (con medio metro de margen para no comerse su piso)
                inside *= step(0.0, t) * (1.0 - smoothstep(la - 1.0, la - 0.5, t));
                mask = max(mask, inside);
            }
            return mask;
        }
        ENDHLSL

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode" = "UniversalForward" }

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_local _ _NINDO_WIND
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #pragma multi_compile_fragment _ _SHADOWS_SOFT
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float2 uv : TEXCOORD0;
                float4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 positionWS : TEXCOORD1;
                float3 normalWS : TEXCOORD2;
                float fogFactor : TEXCOORD3;
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                half3 vertexLight : TEXCOORD4;
                #endif
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes input)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                float3 positionWS = Displace(TransformObjectToWorld(input.positionOS.xyz), input.color);
                o.positionWS = positionWS;
                o.positionCS = TransformWorldToHClip(positionWS);
                o.normalWS = TransformObjectToWorldNormal(input.normalOS);
                o.uv = TRANSFORM_TEX(input.uv, _BaseMap);
                o.fogFactor = ComputeFogFactor(o.positionCS.z);
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                o.vertexLight = VertexLighting(positionWS, o.normalWS);
                #endif
                return o;
            }

            half3 Diffuse(Light light, half3 normalWS)
            {
                half ndl = dot(normalWS, light.direction);
                half wrapped = saturate((ndl + _Wrap) / (1.0h + _Wrap));
                return light.color * (wrapped * light.distanceAttenuation * light.shadowAttenuation);
            }

            half4 frag(Varyings input, FRONT_FACE_TYPE facing : FRONT_FACE_SEMANTIC) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                float fade = max(_NindoFade, _NindoHoleFade * HoleMask(input.positionWS));
                clip(Bayer4(input.positionCS.xy) - fade);

                half4 albedo = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, input.uv) * _BaseColor;
                half3 normalWS = normalize(input.normalWS);
                normalWS = IS_FRONT_VFACE(facing, true, false) ? normalWS : -normalWS;

                float4 shadowCoord = TransformWorldToShadowCoord(input.positionWS);
                Light mainLight = GetMainLight(shadowCoord, input.positionWS, half4(1, 1, 1, 1));
                half3 lighting = Diffuse(mainLight, normalWS) + SampleSH(normalWS);

                #if defined(_ADDITIONAL_LIGHTS)
                InputData inputData = (InputData)0;
                inputData.positionWS = input.positionWS;
                inputData.normalWS = normalWS;
                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);
                uint lightCount = GetAdditionalLightsCount();
                #if USE_CLUSTER_LIGHT_LOOP
                [loop] for (uint dirIndex = 0u; dirIndex < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS); dirIndex++)
                    lighting += Diffuse(GetAdditionalLight(dirIndex, input.positionWS, half4(1, 1, 1, 1)), normalWS);
                #endif
                LIGHT_LOOP_BEGIN(lightCount)
                    Light light = GetAdditionalLight(lightIndex, input.positionWS, half4(1, 1, 1, 1));
                    lighting += Diffuse(light, normalWS);
                LIGHT_LOOP_END
                #endif
                #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                lighting += input.vertexLight;
                #endif

                half3 emission = SAMPLE_TEXTURE2D(_EmissionMap, sampler_BaseMap, input.uv).rgb * _EmissionColor.rgb;
                // el Lit de la paleta (metálico 0) refleja un 4 % como especular y difunde el 96 %: sin esto el objeto se
                // aclaraba de golpe al cambiar de material
                half3 color = albedo.rgb * _DiffuseScale * lighting + emission;
                color = MixFog(color, input.fogFactor);
                return half4(color, 1.0h);
            }
            ENDHLSL
        }

        // la sombra se disuelve menos que el objeto (_NindoShadowFade): lo pegado a la cámara no deja sombras
        // fantasma enteras sobre la pelea, pero el suelo no "salta" de sombra a luz. Con hueco (una copa o un techo
        // sobre Kaito) la sombra entera se aclara a la mitad de eso: desde la luz no se sabe dónde cae el cono
        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode" = "ShadowCaster" }
            ZWrite On
            ZTest LEqual
            ColorMask 0

            HLSLPROGRAM
            #pragma vertex vertShadow
            #pragma fragment fragShadow
            #pragma multi_compile_local _ _NINDO_WIND
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Shadows.hlsl"

            float3 _LightDirection;
            float3 _LightPosition;

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings { float4 positionCS : SV_POSITION; };

            Varyings vertShadow(Attributes input)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(input);
                float3 positionWS = Displace(TransformObjectToWorld(input.positionOS.xyz), input.color);
                float3 normalWS = TransformObjectToWorldNormal(input.normalOS);
                #if defined(_CASTING_PUNCTUAL_LIGHT_SHADOW)
                    float3 lightDirectionWS = normalize(_LightPosition - positionWS);
                #else
                    float3 lightDirectionWS = _LightDirection;
                #endif
                float4 positionCS = TransformWorldToHClip(ApplyShadowBias(positionWS, normalWS, lightDirectionWS));
                #if UNITY_REVERSED_Z
                    positionCS.z = min(positionCS.z, UNITY_NEAR_CLIP_VALUE);
                #else
                    positionCS.z = max(positionCS.z, UNITY_NEAR_CLIP_VALUE);
                #endif
                o.positionCS = positionCS;
                return o;
            }

            half4 fragShadow(Varyings input) : SV_Target
            {
                clip(Bayer4(input.positionCS.xy) - max(_NindoFade, _NindoHoleFade * 0.5) * _NindoShadowFade);
                return 0;
            }
            ENDHLSL
        }

        // profundidad con la misma trama: el SSAO y el DOF no dibujan el contorno de lo que ya no se ve
        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode" = "DepthOnly" }
            ZWrite On
            ColorMask R

            HLSLPROGRAM
            #pragma vertex vertDepth
            #pragma fragment fragDepth
            #pragma multi_compile_local _ _NINDO_WIND
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                float4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings { float4 positionCS : SV_POSITION; float3 positionWS : TEXCOORD0; };

            Varyings vertDepth(Attributes input)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(input);
                o.positionWS = Displace(TransformObjectToWorld(input.positionOS.xyz), input.color);
                o.positionCS = TransformWorldToHClip(o.positionWS);
                return o;
            }

            half4 fragDepth(Varyings input) : SV_Target
            {
                clip(Bayer4(input.positionCS.xy) - max(_NindoFade, _NindoHoleFade * HoleMask(input.positionWS)));
                return input.positionCS.z;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode" = "DepthNormals" }
            ZWrite On

            HLSLPROGRAM
            #pragma vertex vertDepthNormals
            #pragma fragment fragDepthNormals
            #pragma multi_compile_local _ _NINDO_WIND
            #pragma multi_compile_instancing

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 normalWS : TEXCOORD0;
                float3 positionWS : TEXCOORD1;
            };

            Varyings vertDepthNormals(Attributes input)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(input);
                o.positionWS = Displace(TransformObjectToWorld(input.positionOS.xyz), input.color);
                o.positionCS = TransformWorldToHClip(o.positionWS);
                o.normalWS = TransformObjectToWorldNormal(input.normalOS);
                return o;
            }

            half4 fragDepthNormals(Varyings input, FRONT_FACE_TYPE facing : FRONT_FACE_SEMANTIC) : SV_Target
            {
                clip(Bayer4(input.positionCS.xy) - max(_NindoFade, _NindoHoleFade * HoleMask(input.positionWS)));
                float3 n = normalize(input.normalWS);
                n = IS_FRONT_VFACE(facing, true, false) ? n : -n;
                return half4(n, 0.0);
            }
            ENDHLSL
        }
    }

    FallBack Off
}
