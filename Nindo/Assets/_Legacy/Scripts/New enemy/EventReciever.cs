using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class EventReciever : MonoBehaviour
{
    public EnemyCombat enemyCombat;

    // 📍 Se llama desde el Animation Event cuando el ataque empieza
    public void StartAttack()
    {
        enemyCombat.isAttacking = true;
    }

    // 📍 Se llama justo en el frame del impacto
    public void DealDamage()
    {
        enemyCombat.TryDealDamageToPlayer();
    }

    // 📍 Se llama cuando termina la animación del ataque
    public void StopAttack()
    {
        enemyCombat.isAttacking = false;
        enemyCombat.hasDealtDamage = false;
    }

    public void ComboEnd() 
    {
        enemyCombat.ComboEnd();
    }
    public void OnParryAnimationEnd()
    {
        enemyCombat.OnParryAnimationEnd();
    }

}
