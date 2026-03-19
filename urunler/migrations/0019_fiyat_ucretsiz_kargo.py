from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('urunler', '0018_urun_durum'),
    ]

    operations = [
        migrations.AddField(
            model_name='fiyat',
            name='ucretsiz_kargo',
            field=models.BooleanField(default=False, help_text='Ücretsiz kargo bilgisi eBay/API tarafından doğrulandı mı?'),
        ),
    ]