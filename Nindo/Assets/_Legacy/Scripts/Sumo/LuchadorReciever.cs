using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class LuchadorReciever : MonoBehaviour
{
    public LuchadorCombat luchadorCombat;

    // 📍 Se llama desde el Animation Event cuando el ataque empieza
    public void StartAttack()
    {
        luchadorCombat.isAttacking = true;
    }

    // 📍 Se llama justo en el frame del impacto
    public void DealDamage()
    {
        luchadorCombat.TryDealDamageToPlayer();
    }

    // 📍 Se llama cuando termina la animación del ataque
    public void StopAttack()
    {
        luchadorCombat.isAttacking = false;
        luchadorCombat.hasDealtDamage = false;
    }
    public void ComboEnd()
    {
        luchadorCombat.ComboEnd();
    }
}
